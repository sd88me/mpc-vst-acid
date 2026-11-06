// Acid for MPC / Force: the MPC Plugin SDK front end (framework/mpc_plugin.h) around the unchanged generator (src/acid_core.c,
// driven through its string API in acid_core.h).
//
// Acid makes no sound. It is a MIDI generator: the notes go out of an ALSA sequencer port named "Acid" (a second instance "Acid 2"),
// because the MPC discards a plugin's VST MIDI output (SDK docs/host-contract.md). The user routes a track's MIDI input from that port.
//
// Signal flow, per audio block (process): host transport -> a synthetic 24-PPQN clock plus one 0xF9 "song step" per 16th, placed on the
// song-position grid (swing delays the odd ones) -> the core -> ALSA. Incoming MIDI (live transpose) goes to the core as well.
//
// Parameters: 217 engine parameters in vst/params.lock order (tools/gen_sdk_params.py -> params_gen.h) plus the UI-only "ui_open".
//   * value params: a change goes to the core at once as its own set_param string.
//   * momentary params (GENERATE, MUTATE): 0 -> 1 fires the verb once, then the param drops back to 0 (worker thread).
//   * pushed params: the core changes them behind the host's back (edit-page cells after Generate / density moves, the BLEND snap in
//     Chain mode, the running lights, the Chain readout); a worker thread reads them back and tells the host.
// Parameter 0 is GENERATE (frozen order). The host nudges parameter 0 to 1 and straight back on every prepare: a press counts only once it
// has stayed high for ~40 ms, so the nudge never re-rolls the pattern.
// State: the framework saves every parameter by id; the seeds and the hand-locked steps go in the extra state and are applied last.
// A project saved by the 2.x wrapper build ("key=value;" text) is still read (effSetChunk is wrapped in VSTPluginMain below).

#include "mpc_plugin.h"

extern "C" {
#include "acid_core.h"
}
#include "params_gen.h"

#include <alsa/asoundlib.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#ifndef ACID_NAME
#define ACID_NAME "Acid"
#endif
#ifndef ACID_UID
#define ACID_UID 'A', 'c', 'I', 'd'
#endif
#define ACID_FOURCC(...) MPC_FOURCC(__VA_ARGS__)   // expands ACID_UID before MPC_FOURCC counts its arguments
#ifndef ACID_VERSION
#define ACID_VERSION 3000
#endif

namespace {

// ---- process-wide host callbacks: the MPC has one transport for every track, so the core's bpm / clock hooks are globals ----
std::atomic<float> g_bpm{120.0f};
std::atomic<int> g_clock{MOVE_CLOCK_STATUS_STOPPED};
float hostBpm() { return g_bpm.load(); }
int hostClock() { return g_clock.load(); }
const host_api_v1_t g_host = {hostBpm, hostClock};
midi_fx_api_v1_t* g_api = nullptr;
std::mutex g_apiInit;
std::atomic<unsigned> g_slots{0};   // ALSA client names: "Acid" for the first free slot, "Acid 2", ... (a slot is freed when its instance closes)

mpc::PluginInfo makeInfo()
{
    mpc::PluginInfo i;
    i.name = ACID_NAME;
    i.vendor = "sd88me";
    i.uniqueId = ACID_FOURCC(ACID_UID);
    i.version = ACID_VERSION;
    i.isInstrument = true;
    i.numInputs = 0;
    i.numOutputs = 2;
    return i;
}

long long nowMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

} // namespace

class AcidPlugin : public mpc::Plugin
{
public:
    AcidPlugin() : mpc::Plugin(makeInfo())
    {
        for (int i = 0; i < kNumParams; ++i)
        {
            const PSpec& s = g_pspecs[i];
            if (s.flags & kChoice)
                addParam(mpc::choiceParam(s.key, s.name, std::vector<std::string>(s.choices, s.choices + s.nchoices), (int)s.def));
            else if (s.flags & kFloat)
                addParam(mpc::floatParam(s.key, s.name, s.min, s.max, s.def, "", 2));
            else
                addParam(mpc::intParam(s.key, s.name, (int)s.min, s.max > s.min ? (int)s.max : (int)s.min + 1, (int)s.def));
        }
        const size_t n = (size_t)kNumParams;
        held_ = new std::atomic<bool>[n];
        release_ = new std::atomic<bool>[n];
        for (size_t i = 0; i < n; ++i) { held_[i].store(false); release_[i].store(false); }
        told_.assign(n, -1.0e9f);
        iMute_ = indexOf("mute");
        iSwing_ = indexOf("swing");
        iBar_[0] = indexOf("a_edit_bar"); iBar_[1] = indexOf("b_edit_bar");
        iRun_[0] = indexOf("a_run"); iRun_[1] = indexOf("b_run");

        {
            std::lock_guard<std::mutex> lk(g_apiInit);
            if (!g_api) g_api = move_midi_fx_init(&g_host);
        }
        if (g_api && g_api->api_version == MIDI_FX_API_VERSION) inst_ = g_api->create_instance(".", nullptr);
        alsaOpen();
        worker_ = std::thread(&AcidPlugin::workerMain, this);
    }

    ~AcidPlugin() override
    {
        quit_.store(true);
        if (worker_.joinable()) worker_.join();
        alsaClose();
        if (inst_) g_api->destroy_instance(inst_);
        delete[] held_;
        delete[] release_;
    }

    void prepare(double, int) override {}

    // Audio thread, on resume and after a state load.
    void reset() override
    {
        store(kUiParam, 0.0f);
        notify_.store(true);
        resync_.store(true);
    }

    // ---- the audio callback ---------------------------------------------------------------------------------------------------
    void process(mpc::ProcessContext& ctx) override
    {
        if (!inst_) return;
        feedTransport(ctx);
        for (int k = 0; k < ctx.numMidiEvents; ++k)
        {
            const mpc::MidiEvent& e = ctx.midi[k];
            if (e.size < 2 || wasJustSent(e.data)) continue;
            uint8_t out[MIDI_FX_MAX_OUT_MSGS][3];
            int olen[MIDI_FX_MAX_OUT_MSGS];
            uint8_t in[3] = {e.data[0], e.data[1], e.size > 2 ? e.data[2] : (uint8_t)0};
            int n;
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->process_midi(inst_, in, 3, out, olen, MIDI_FX_MAX_OUT_MSGS); }
            alsaSend(out, olen, n);
        }
        uint8_t out[MIDI_FX_MAX_OUT_MSGS][3];
        int olen[MIDI_FX_MAX_OUT_MSGS];
        int n;
        { std::lock_guard<std::mutex> lk(lock_); n = g_api->tick(inst_, ctx.numFrames, MOVE_SAMPLE_RATE, out, olen, MIDI_FX_MAX_OUT_MSGS); }
        alsaSend(out, olen, n);
    }

    // ---- parameters -----------------------------------------------------------------------------------------------------------
    // Any thread. Value changes go straight to the core.
    void parameterChanged(int index, float plain) override
    {
        if (index < 0 || index >= kNumParams || !inst_) return;
        const PSpec& s = g_pspecs[index];
        if (s.flags & kUi) return;
        if ((s.flags & kChoice) && get(kUiParam) > 0.5f)   // a pick from the open drawn list closes it
        {
            store(kUiParam, 0.0f);
            notify_.store(true);
        }
        if (s.flags & kReadOnly) return;
        if (s.flags & kMomentary)
        {
            if (plain < 0.5f) { held_[index].store(false); if (index == 0) pending0_.store(0); return; }
            if (held_[index].exchange(true)) return;   // an echo of our own release must not fire twice
            if (index == 0) { pending0_.store(nowMs()); return; }   // debounced in the worker, see the header comment
            fire(index);
            return;
        }
        if (loading_.load() && (s.flags & kEditCell)) return;   // derived from the pattern: a state load must not lock the steps it shows
        if (s.flags & kPushed) told_[(size_t)index] = plain;   // the host already has this value: don't echo it back
        char buf[32];
        if (s.flags & kFloat) std::snprintf(buf, sizeof buf, "%g", (double)plain);
        else std::snprintf(buf, sizeof buf, "%d", (int)std::lround(plain));
        std::lock_guard<std::mutex> lk(lock_);
        g_api->set_param(inst_, s.key, buf);
    }

    // A small value range shown as a percentage (density, accent, slide, gate, jitter).
    bool formatValue(int index, float plain, std::string& out) override
    {
        if (index < 0 || index >= kNumParams) return false;
        if (g_pspecs[index].flags & kMomentary) { out = ""; return true; }
        if (!(g_pspecs[index].flags & kFloat)) return false;
        const float range = g_pspecs[index].max - g_pspecs[index].min;
        char b[16];
        std::snprintf(b, sizeof b, "%ld", std::lround(range > 0 ? (plain - g_pspecs[index].min) / range * 100.0f : plain));
        out = b;
        return true;
    }

    // ---- state ------------------------------------------------------------------------------------------------------------------
    // The pattern each GENERATE made, and the hand-locked steps: not parameters, so they travel as text.
    void saveExtraState(std::vector<uint8_t>& out) override
    {
        if (!inst_) return;
        std::string s;
        for (const char* k : {"a_seed", "b_seed", "a_locks", "b_locks"})
        {
            char buf[512];
            int n;
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->get_param(inst_, k, buf, sizeof buf); }
            if (n <= 0) continue;
            buf[n < (int)sizeof buf ? n : (int)sizeof buf - 1] = 0;
            s += k; s += '='; s += buf; s += ';';
        }
        out.assign(s.begin(), s.end());
    }

    void loadExtraState(const uint8_t* data, size_t size) override
    {
        if (!inst_ || !data) return;
        applyText(std::string(reinterpret_cast<const char*>(data), size));
    }

    // A project saved by the wrapper build: "key=value;..." (values in the core's own units). Called from the wrapped effSetChunk.
    bool loadLegacy(const char* data, size_t size)
    {
        if (!inst_ || !data || size == 0) return false;
        std::string s(data, strnlen(data, size));
        if (s.find('=') == std::string::npos) return false;
        loading_.store(true);
        if (s.find("a_seed=") == std::string::npos)   // saved before seeds were stored: keep the old fixed default pattern
        {
            std::lock_guard<std::mutex> lk(lock_);
            g_api->set_param(inst_, "a_seed", "48879");
            g_api->set_param(inst_, "b_seed", "48880");
        }
        applyText(s);
        loading_.store(false);
        resync_.store(true);
        return true;
    }

    std::atomic<bool> loading_{false};   // set around a state load (wrapped effSetChunk)
    void requestResync() { resync_.store(true); }

private:
    int indexOf(const char* key) const
    {
        for (int i = 0; i < kNumParams; ++i) if (!std::strcmp(g_pspecs[i].key, key)) return i;
        return -1;
    }

    // Set a parameter's value without calling parameterChanged (so it is not written back to the core).
    void store(int i, float plain) { values_[(size_t)i]->store(param(i).toNormalised(plain), std::memory_order_relaxed); }

    void fire(int index)
    {
        { std::lock_guard<std::mutex> lk(lock_); g_api->set_param(inst_, g_pspecs[index].key, "go"); }
        release_[index].store(true);
    }

    // "key=value;key=value": the core's own keys (legacy chunks carry every parameter, the new extra state only seeds and locks).
    void applyText(const std::string& s)
    {
        size_t pos = 0;
        while (pos < s.size())
        {
            size_t end = s.find(';', pos);
            if (end == std::string::npos) end = s.size();
            const std::string tok = s.substr(pos, end - pos);
            pos = end + 1;
            const size_t eq = tok.find('=');
            if (eq == std::string::npos) continue;
            const std::string key = tok.substr(0, eq), val = tok.substr(eq + 1);
            const int i = indexOf(key.c_str());
            if (i >= 0 && !(g_pspecs[i].flags & (kUi | kMomentary | kReadOnly | kEditCell)))
            {
                float v = (float)std::atof(val.c_str());
                v = std::min(std::max(v, g_pspecs[i].min), g_pspecs[i].max);
                set(i, v);   // framework value + parameterChanged -> the core
            }
            else if (i < 0)
            {
                std::lock_guard<std::mutex> lk(lock_);
                g_api->set_param(inst_, key.c_str(), val.c_str());
            }
        }
    }

    // ---- ALSA sequencer output ------------------------------------------------------------------------------------------------
    void alsaOpen()
    {
        if (snd_seq_open(&seq_, "default", SND_SEQ_OPEN_OUTPUT, SND_SEQ_NONBLOCK) < 0) { seq_ = nullptr; return; }
        snd_seq_set_client_pool_output(seq_, 2048);   // headroom so a slow subscriber never stalls the audio thread
        unsigned cur = g_slots.load();
        for (;;)
        {
            slot_ = 0;
            while (slot_ < 31 && (cur & (1u << slot_))) ++slot_;
            if (g_slots.compare_exchange_weak(cur, cur | (1u << slot_))) break;
        }
        char name[32];
        if (slot_ == 0) std::snprintf(name, sizeof name, "%s", ACID_NAME);
        else std::snprintf(name, sizeof name, "%s %d", ACID_NAME, slot_ + 1);
        snd_seq_set_client_name(seq_, name);
        port_ = snd_seq_create_simple_port(seq_, "MIDI Out", SND_SEQ_PORT_CAP_READ | SND_SEQ_PORT_CAP_SUBS_READ,
                                           SND_SEQ_PORT_TYPE_MIDI_GENERIC | SND_SEQ_PORT_TYPE_APPLICATION);
    }

    void alsaClose()
    {
        if (!seq_) return;
        for (int ch = 0; ch < 16; ch++)
            for (int note = 0; note < 128; note++)
            {
                snd_seq_event_t ev;
                snd_seq_ev_clear(&ev);
                snd_seq_ev_set_source(&ev, port_);
                snd_seq_ev_set_subs(&ev);
                snd_seq_ev_set_direct(&ev);
                snd_seq_ev_set_noteoff(&ev, ch, note, 0);
                snd_seq_event_output_direct(seq_, &ev);
            }
        snd_seq_close(seq_);
        seq_ = nullptr;
        if (slot_ >= 0) g_slots.fetch_and(~(1u << slot_));
    }

    void alsaSend(const uint8_t (*msgs)[3], const int* lens, int n)
    {
        const bool muted = iMute_ >= 0 && getBool(iMute_);   // muted: swallow note-ons, keep note-offs so nothing hangs
        for (int i = 0; i < n; i++)
        {
            if (lens[i] < 2) continue;
            sent_[sentPos_][0] = msgs[i][0];
            sent_[sentPos_][1] = msgs[i][1];
            sent_[sentPos_][2] = lens[i] > 2 ? msgs[i][2] : 0;
            sentPos_ = (sentPos_ + 1) % 16;
            if (sentLen_ < 16) sentLen_++;
        }
        if (!seq_ || port_ < 0) return;
        for (int i = 0; i < n; i++)
        {
            const uint8_t* m = msgs[i];
            const int len = lens[i];
            if (len < 2) continue;
            if (muted && (m[0] & 0xF0) == 0x90 && len >= 3 && m[2] > 0) continue;
            snd_seq_event_t ev;
            snd_seq_ev_clear(&ev);
            snd_seq_ev_set_source(&ev, port_);
            snd_seq_ev_set_subs(&ev);
            snd_seq_ev_set_direct(&ev);
            const uint8_t type = m[0] & 0xF0, ch = m[0] & 0x0F;
            if (type == 0x90 && len >= 3 && m[2] > 0) snd_seq_ev_set_noteon(&ev, ch, m[1], m[2]);
            else if (type == 0x80 || (type == 0x90 && len >= 3)) snd_seq_ev_set_noteoff(&ev, ch, m[1], 0);
            else if (type == 0xB0 && len >= 3) snd_seq_ev_set_controller(&ev, ch, m[1], m[2]);
            else continue;
            snd_seq_event_output(seq_, &ev);   // buffered, non-blocking: drops instead of hanging
        }
        snd_seq_drain_output(seq_);
    }

    // Loop guard: MPC record-arm / input monitor can route this plugin's own ALSA output straight back in as MIDI, and the core would
    // treat the echoed notes as live transpose. Remember the last few messages sent; drop an incoming one that matches, once.
    // Match on status + data1 only: the velocity does not come back byte-exact (72 -> 71, a note-off's 0 -> 64).
    bool wasJustSent(const uint8_t* m)
    {
        for (int i = 0; i < sentLen_; i++)
        {
            const int idx = (sentPos_ - 1 - i + 16) % 16;
            if (sent_[idx][0] == m[0] && sent_[idx][1] == m[1]) { sent_[idx][0] = 0xFF; return true; }
        }
        return false;
    }

    // ---- transport -> the core's clock ------------------------------------------------------------------------------------------
    // Send the song positions [start, end): 16th-note steps on the song-position grid (swing delays the odd ones), then the 24-PPQN
    // heartbeat pulses. Steps go first so the core is already grid-driven when the pulses arrive.
    void playSpan(double start, double end)
    {
        const double step = 1.0 / 24.0;   // 24 PPQN, in quarter notes
        uint8_t out[MIDI_FX_MAX_OUT_MSGS][3];
        int olen[MIDI_FX_MAX_OUT_MSGS];
        const int pct = iSwing_ >= 0 ? getInt(iSwing_) : 50;
        const double d = pct > 50 ? std::min(0.5, (pct - 50) / 50.0) : 0.0;
        const long n0 = (long)std::floor(start * 4.0) - 1, n1 = (long)std::ceil(end * 4.0) + 1;
        for (long k = n0 < 0 ? 0 : n0; k <= n1; k++)
        {
            const double t = k * 0.25 + ((k & 1) ? d * 0.25 : 0.0);
            if (t < start - 1e-9 || t >= end - 1e-9) continue;
            // Each step names its absolute 16th in the song: the core plays the pattern step that song position calls for, so a doubled
            // or lost host step (fast tempo changes do both) can't shift it. A 16th already fired is skipped so no note doubles.
            if (nextK_ >= 0 && k < nextK_) continue;
            char kb[24];
            std::snprintf(kb, sizeof kb, "%ld", k);
            uint8_t st = 0xF9;
            int n;
            { std::lock_guard<std::mutex> lk(lock_);
              g_api->set_param(inst_, "song_step", kb);
              n = g_api->process_midi(inst_, &st, 1, out, olen, MIDI_FX_MAX_OUT_MSGS); }
            alsaSend(out, olen, n);
            nextK_ = k + 1;
            ++steps_;
        }
        for (double next = std::ceil(start / step - 1e-9) * step; next < end - 1e-9; next += step)
        {
            uint8_t msg = 0xF8;
            int n;
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->process_midi(inst_, &msg, 1, out, olen, MIDI_FX_MAX_OUT_MSGS); }
            alsaSend(out, olen, n);
        }
    }

    void feedTransport(const mpc::ProcessContext& ctx)
    {
        const mpc::Transport& t = ctx.transport;
        const bool playing = t.valid && t.playing;
        if (t.valid && t.tempoValid && t.bpm > 0) g_bpm.store((float)t.bpm);   // the core's gate lengths and fallback clock use this
        uint8_t out[MIDI_FX_MAX_OUT_MSGS][3];
        int olen[MIDI_FX_MAX_OUT_MSGS];
        uint8_t msg[1];

        if (playing && !wasPlaying_)
        {
            g_clock.store(MOVE_CLOCK_STATUS_RUNNING);
            lastPpq_ = t.ppqPos;
            nextK_ = -1;
            int n;
            msg[0] = 0xFA;
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->process_midi(inst_, msg, 1, out, olen, MIDI_FX_MAX_OUT_MSGS); }
            alsaSend(out, olen, n);
            uint8_t arm[2] = {0xF9, 1};   // from here the core steps on 0xF9 boundaries; 0xF8 is only a sync heartbeat
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->process_midi(inst_, arm, 2, out, olen, MIDI_FX_MAX_OUT_MSGS); }
        }
        else if (!playing && wasPlaying_)
        {
            g_clock.store(MOVE_CLOCK_STATUS_STOPPED);
            msg[0] = 0xFC;
            int n;
            { std::lock_guard<std::mutex> lk(lock_); n = g_api->process_midi(inst_, msg, 1, out, olen, MIDI_FX_MAX_OUT_MSGS); }
            alsaSend(out, olen, n);
        }
        wasPlaying_ = playing;
        playingNow_.store(playing);

        if (!playing) return;
        // The steps of THIS block, [ppq, ppq + blk), go out now, at its start: up to a block early instead of a block late. MPC's MIDI
        // input comes after the plugin, so earlier is closer to the grid. lastPpq_ is the high-water mark: everything before it is sent.
        const double bpm = t.bpm > 0 ? t.bpm : g_bpm.load();
        const double blk = ctx.numFrames * bpm / (60.0 * (ctx.sampleRate > 0 ? ctx.sampleRate : 44100.0));
        const double p = t.ppqPos;
        double start = lastPpq_;
        const double end = p + blk;
        // MPC's loop (verified on a Force, MPC OS 3.9.1: cycle flags set, cycleStart/EndPos = the loop; the block before a wrap covers
        // the loop end, the next reports a position just after the loop start).
        const bool cyc = t.cycling && t.cycleEndPpq > t.cycleStartPpq + 0.25;
        const double ls = cyc ? t.cycleStartPpq : 0.0, le = cyc ? t.cycleEndPpq : 0.0;
        // p behind what was sent by less than a beat: block jitter (the host's ppq wobbles up to 0.0009 beat) or a tempo change: keep the
        // high-water mark, so nothing plays twice. By more: a wrap the host did not report, or a locate. The block before was covered by
        // the look-ahead, so carry on from here, less a little more than the jitter (a wrap reported at 0.0001 still plays the loop
        // start's 16th) -- except after an unreported wrap, whose loop start the look-ahead may already have played.
        if (std::fabs(p - start) > 1.0)
        {
            const bool inLoop = cyc && p >= ls - 0.002 && p < le;
            start = inLoop ? std::max(p - 0.002, ls) : p < start ? p : p - 0.002;
            nextK_ = -1;
        }
        if (end > start)
        {
            if (cyc && p >= ls && p < le && end > le)   // the loop end falls in this block: up to it, then on from the loop start
            {
                playSpan(start, le);
                nextK_ = -1;
                lastPpq_ = ls + (end - le);
                playSpan(ls, lastPpq_);
            }
            else
            {
                playSpan(start, end);
                lastPpq_ = end;
            }
        }
    }

    // ---- worker: momentary releases, the host-visible state the core changes by itself ---------------------------------------------
    bool readEngine(int i, float& plain, bool clampToRange = true)
    {
        char buf[64];
        int n;
        { std::lock_guard<std::mutex> lk(lock_); n = g_api->get_param(inst_, g_pspecs[i].key, buf, sizeof buf); }
        if (n <= 0) return false;
        buf[n < (int)sizeof buf ? n : (int)sizeof buf - 1] = 0;
        plain = (float)std::atof(buf);
        if (clampToRange) plain = std::min(std::max(plain, g_pspecs[i].min), g_pspecs[i].max);
        return true;
    }

    void pushValue(int i, float plain)
    {
        told_[(size_t)i] = plain;
        store(i, plain);
        notifyHostParameterChanged(i);
    }

    void workerMain()
    {
        while (!quit_.load())
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            tickOnce(false);
        }
    }

    // One worker pass. force = the offline test: fire a pending GENERATE at once and read back everything.
    void tickOnce(bool force)
    {
        if (!inst_) return;
        // GENERATE on parameter 0 counts only after ~40 ms high
        const long long p0 = pending0_.load();
        if (p0 && (force || nowMs() - p0 >= 40)) { pending0_.store(0); fire(0); }
        for (int i = 0; i < kNumParams; ++i)
            if (release_[i].load()) { release_[i].store(false); held_[i].store(false); store(i, 0.0f); notifyHostParameterChanged(i); }
        if (notify_.exchange(false)) notifyHostParameterChanged(kUiParam);
        if (resync_.exchange(false)) std::fill(told_.begin(), told_.end(), -1.0e9f);

        // the running lights: 1..16 = the playing step's column in the bar shown, 0 = none
        for (int b = 0; b < 2; ++b)
        {
            if (iRun_[b] < 0) continue;
            float col = 0.0f, run = 0.0f, bar = 0.0f;
            if (playingNow_.load() && readEngine(iRun_[b], run, false) && readEngine(iBar_[b], bar))
            {
                const int r = (int)run;
                col = r > 0 && (r - 1) / 16 == (int)bar ? (float)((r - 1) % 16 + 1) : 0.0f;
            }
            if (col != told_[(size_t)iRun_[b]]) pushValue(iRun_[b], col);
        }
        // everything else the core changes behind the host's back: a bounded number per pass, round-robin
        int budget = force ? kNumParams : 24;
        const int first = cursor_;
        for (int k = 0; k < kNumParams && budget > 0; ++k)
        {
            const int i = (first + k) % kNumParams;
            const int fl = g_pspecs[i].flags;
            if (!(fl & kPushed) || iRun_[0] == i || iRun_[1] == i) continue;
            float v;
            if (!readEngine(i, v) || v == told_[(size_t)i]) continue;
            pushValue(i, v);
            --budget;
            cursor_ = (i + 1) % kNumParams;
        }
    }

public:
#ifdef ACID_TEST
    long dbgSteps() const { return steps_; }
    int dbgPos()
    {
        char b[16] = {0};
        std::lock_guard<std::mutex> lk(lock_);
        g_api->get_param(inst_, "a_pos", b, sizeof b);
        return std::atoi(b);
    }
    int dbgSync()
    {
        tickOnce(true);
        int bad = 0;   // host-visible value != the core's
        for (int i = 0; i < kNumParams; ++i)
        {
            float v;
            if ((g_pspecs[i].flags & kPushed) && !(g_pspecs[i].flags & kReadOnly) && readEngine(i, v) && std::fabs(get(i) - v) > 0.01f) ++bad;
        }
        return bad;
    }
#endif
private:
    void* inst_ = nullptr;
    std::mutex lock_;   // serialises every call into the (single-threaded) core; held for microseconds
    std::thread worker_;
    std::atomic<bool> quit_{false};
    std::atomic<bool> notify_{false}, resync_{false}, playingNow_{false};
    std::atomic<long long> pending0_{0};
    std::atomic<bool>* held_ = nullptr;
    std::atomic<bool>* release_ = nullptr;
    std::vector<float> told_;   // the value the host was last told, per pushed parameter
    int iMute_ = -1, iSwing_ = -1, iBar_[2] = {-1, -1}, iRun_[2] = {-1, -1};
    snd_seq_t* seq_ = nullptr;
    int port_ = -1, slot_ = -1;
    uint8_t sent_[16][3] = {{0}};
    int sentLen_ = 0, sentPos_ = 0;
    bool wasPlaying_ = false;
    double lastPpq_ = 0.0;
    int cursor_ = 0;
    long steps_ = 0;
    long nextK_ = -1;   // next absolute 16th index due; -1 = rebase on the next step (start, loop wrap, locate)
};

// The same entry as MPC_PLUGIN_ENTRY, plus a wrapped effSetChunk: a "MPCP" chunk loads with the pattern-derived edit cells ignored, a
// legacy text chunk from the wrapper build is read as before.
namespace {
VstIntPtr (*g_origDispatcher)(AEffect*, VstInt32, VstInt32, VstIntPtr, void*, float) = nullptr;

VstIntPtr acidDispatcher(AEffect* e, VstInt32 opcode, VstInt32 index, VstIntPtr value, void* ptr, float opt)
{
    if (opcode == effSetChunk && e->object && ptr)
    {
        AcidPlugin* p = static_cast<AcidPlugin*>(e->object);
        if (value >= 4 && std::memcmp(ptr, "MPCP", 4) == 0)
        {
            p->loading_.store(true);
            const VstIntPtr r = g_origDispatcher(e, opcode, index, value, ptr, opt);
            p->loading_.store(false);
            p->requestResync();
            return r;
        }
        return p->loadLegacy(static_cast<const char*>(ptr), (size_t)value) ? 1 : 0;
    }
    return g_origDispatcher(e, opcode, index, value, ptr, opt);
}
} // namespace

#ifdef ACID_TEST   // offline test hooks (vst/host_test.cpp); absent from the release build
extern "C" MPC_EXPORT long acid_dbg_steps(AEffect* e) { return static_cast<AcidPlugin*>(e->object)->dbgSteps(); }
extern "C" MPC_EXPORT float acid_dbg_bpm() { return g_bpm.load(); }
extern "C" MPC_EXPORT int acid_dbg_pos(AEffect* e) { return static_cast<AcidPlugin*>(e->object)->dbgPos(); }
extern "C" MPC_EXPORT int acid_dbg_sync(AEffect* e) { return static_cast<AcidPlugin*>(e->object)->dbgSync(); }
#endif

extern "C" MPC_EXPORT AEffect* VSTPluginMain(audioMasterCallback host)
{
    if (host != nullptr && host(nullptr, audioMasterVersion, 0, 0, nullptr, 0.0f) == 0) return nullptr;   // host is VST1 only
    AEffect* e = mpc::detail::createEffect(new AcidPlugin(), host);
    if (e && !g_origDispatcher) g_origDispatcher = e->dispatcher;
    if (e) e->dispatcher = acidDispatcher;
    return e;
}
