I am Nadia Kotecki and I own the build for our metrics rollup service.

The nightly export has failed on every run since the second-to-last release went
out. There is a write-up of it on file, and our release notes are supposed to say
what went into each version. Both were written in a hurry and I am not willing to
repeat anything from either to the platform team until someone has been back over
them against the repository itself.

The platform team will want to know what moved and why nothing we run stopped it,
and they will not accept a package name on its own. Half our team already thinks
this is down to a pin we took off around the same time, and I need that argument
either made properly or killed properly, because if I walk in and blame the wrong
thing twice I lose the room.

What I want from you is the account I can defend end to end: what actually
changed, how it got into a build we never asked to include it, why it was not
caught, and whether we were ever in a position where it could not have happened.
If we were, tell me which releases those were. Give me the evidence at each step
rather than the conclusion, and be careful with our releases, because the tag
names have misled me before. I have lost hours to commits in that window I could
not account for either way. Close on what we change so this cannot happen again;
the board will not let a post-mortem end without that.
