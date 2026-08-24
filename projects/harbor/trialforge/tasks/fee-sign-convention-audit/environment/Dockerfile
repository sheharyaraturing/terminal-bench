FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Harbor supplies its own agent process. Clear the image's sandbox entrypoint so
# it does not compete. Required — do not remove.
ENTRYPOINT []
CMD ["/bin/bash"]

# The finance committee pack extract the desk works from, alongside the exchange
# export already baked into the image at /data. Both are readable through the
# filesystem server.
COPY fixtures/crypto-desk-fee-summary.csv /data/crypto-desk-fee-summary.csv
COPY fixtures/crypto-desk-pack-notes.txt /data/crypto-desk-pack-notes.txt

# The venue's monthly account activity statement, billing the USD wire fees that
# are charged separately from the trade export. Readable through the filesystem
# server alongside the other flat fixtures.
COPY fixtures/venue-account-activity-statement.csv /data/venue-account-activity-statement.csv

# The general ledger extract the desk has never agreed the fee line to. Loaded as
# an extra table in the warehouse so it is queryable alongside the trade ledger.
COPY fixtures/general-ledger-fee-postings.sql /tmp/gl.sql
RUN sqlite3 /data/db/turing.db < /tmp/gl.sql && rm /tmp/gl.sql

COPY fixtures/execution-fee-schedule.txt /data/execution-fee-schedule.txt
COPY fixtures/general-ledger-fee-detail.sql /tmp/gld.sql
RUN sqlite3 /data/db/turing.db < /tmp/gld.sql && rm /tmp/gld.sql
