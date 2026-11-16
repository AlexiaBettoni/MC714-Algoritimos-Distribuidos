#!/bin/bash

docker compose up -d
docker compose logs -f --no-log-prefix |
  grep --line-buffered -E '"event": "(suspect|election_started|election_yielded|coordinator_elected|coordinator_changed)"'
