#!/bin/sh
set -e

# YouTube changes often and old yt-dlp versions stop working, so update on every start.
if [ "${YTDLP_AUTO_UPDATE:-true}" = "true" ]; then
    echo "Updating yt-dlp..."
    pip install --no-cache-dir --quiet --upgrade "yt-dlp[default]" \
        || echo "yt-dlp update failed, continuing with the installed version"
fi
echo "yt-dlp $(yt-dlp --version)"

exec "$@"
