# VibeBeat

A simple, fast MP3 player with playlists, album art, detachable spectrum bars
and Light, Dark and Green-on-Black themes. Built with Python + PySide6.

## Features (v2.0)
- Detachable spectrum window; pops out automatically when minimised
- Bar colours: Fluorescent Green, White, Fluorescent Blue
- Bar styles: Solid or Segmented (Jet Audio style)
- Playlists: save/open XSPF, M3U8, M3U, PLS
- Shuffle, repeat, ID3 tags, album art, drag-and-drop, saved session

## Install (Ubuntu 22.04+, Debian 12+, Mint 21+, Kubuntu)
Download the `.deb` from Releases, then:
    sudo apt install ./vibebeat_2.0.0_amd64.deb

## Windows
Download `vibebeat-windows.zip` from Releases, unzip, run `vibebeat.exe`.

## Run from source
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python main.py

Author: Iqbal Uddin Khan (iqbalsound@yahoo.com). MIT License.
