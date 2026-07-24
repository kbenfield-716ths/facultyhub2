#!/bin/bash
# Download production database from Fly.io for inspection
fly ssh console --app facultyhub -C "sqlite3 /data/moonlighter.db .dump" > fly_moonlighter_dump.sql
