# VibeBeat

A simple, fast MP3 player with a 10-band graphic equalizer, playlists, album art,
detachable spectrum bars and Light, Dark and Green-on-Black themes.
Built with Python + PySide6.

## Features (v3.0)
- Equalizer presets: Flat, Rock, Pop, Vocal, Bass Boosted + manual sliders
- Detachable spectrum window with optional "keep on top"
- Bar colours: Fluorescent Green, White, Blue, Purple; Solid or Segmented bars
- Playlists: save/open XSPF, M3U8, M3U, PLS
- MP3, FLAC, OGG, WAV; shuffle, repeat, album art, saved session

## Install on Ubuntu / Kubuntu / Debian / Mint (APT repository)
    sudo install -d -m 0755 /etc/apt/keyrings
    curl -fsSL https://iqbalsound.github.io/vibebeat/vibebeat.gpg | sudo tee /etc/apt/keyrings/vibebeat.gpg >/dev/null
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/vibebeat.gpg] https://iqbalsound.github.io/vibebeat stable main" | sudo tee /etc/apt/sources.list.d/vibebeat.list
    sudo apt update && sudo apt install vibebeat

Or download the `.deb` from Releases: `sudo apt install ./vibebeat_3.0.0_amd64.deb`
(Ubuntu 22.04+, Debian 12+, Mint 21+, amd64).

## Windows
Download `vibebeat-windows.zip` from Releases, unzip, run `vibebeat.exe`.

## Run from source
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python main.py

Author: Iqbal Uddin Khan (iqbalsound@yahoo.com). MIT License.
