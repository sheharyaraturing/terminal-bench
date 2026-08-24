# Replacement safety contract

The `dotenv replace SOURCE TARGET` operation must satisfy all of these invariants:

1. Read SOURCE completely before changing TARGET. A missing, unreadable, or
   otherwise failed source read leaves TARGET unchanged.
2. Replace the TARGET directory entry transactionally. Never write through an
   existing or broken symbolic link and never create the link's referent.
3. SOURCE remains in place and byte-for-byte unchanged after success or failure.
4. A regular TARGET that already exists keeps its established permission mode.
5. A missing TARGET, or a TARGET that was a symbolic link, becomes a regular
   file with mode `0600`.
6. A failure before the final replacement leaves no partial TARGET and no
   abandoned temporary file.

These rules apply regardless of worker retries. A retry is another attempt at
the same logical operation, not another requested replacement.
