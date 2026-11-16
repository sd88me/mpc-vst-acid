Acid 3.0.1: Regen works with looped sequences, tidier MIDI output.

- Fixed: Regen did nothing when the sequence loop was as short as the Regen interval (a 2-bar loop with Regen at 2 BARS), and fired at the wrong spacing for other loop lengths. It now regenerates every 1/2/4/8/16/32 bars from the start of playback, in a loop or not.
- Changed: on stop, a locate or closing the plugin, Acid releases only the notes it has sounding, instead of sending a note-off for every note on every channel.
- Changed: a muted Acid no longer sends the slide CCs (CC65 / CC1) either; note-offs still go out so nothing hangs.
- Known: with the MPC's ARP on, a generator plugin streaming into a track through its MIDI port can upset the arp while the transport runs. Maze Seq does the same, so this looks like MPC behaviour, not Acid. Turn the arp off, or the port's Track input off, on those tracks.
