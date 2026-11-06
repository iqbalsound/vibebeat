#!/bin/bash
set -e
VERSION=${1:-2.0.0}
PKG=build/vibebeat_${VERSION}_amd64

rm -rf build && mkdir -p $PKG/DEBIAN $PKG/opt $PKG/usr/bin \
  $PKG/usr/share/applications $PKG/usr/share/icons/hicolor/256x256/apps

cp -r dist/vibebeat $PKG/opt/vibebeat
ln -s ../../opt/vibebeat/vibebeat $PKG/usr/bin/vibebeat
cp icon.png $PKG/usr/share/icons/hicolor/256x256/apps/vibebeat.png

cat > $PKG/DEBIAN/control <<EOF
Package: vibebeat
Version: $VERSION
Section: sound
Priority: optional
Architecture: amd64
Depends: libc6, libegl1, libgl1, libpulse0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0
Maintainer: Iqbal Uddin Khan <iqbalsound@yahoo.com>
Homepage: https://github.com/iqbalsound/vibebeat
Description: VibeBeat MP3 player
 A simple, fast MP3 player with playlists (XSPF, M3U, PLS), album art,
 detachable spectrum bars and Light, Dark and Green-on-Black themes.
EOF

cat > $PKG/usr/share/applications/vibebeat.desktop <<EOF
[Desktop Entry]
Name=VibeBeat
Comment=Simple MP3 player
Exec=/usr/bin/vibebeat %F
Icon=vibebeat
Type=Application
Categories=AudioVideo;Audio;Player;
MimeType=audio/mpeg;audio/x-wav;audio/ogg;audio/flac;audio/mp4;
Terminal=false
EOF

chmod 755 $PKG/opt/vibebeat/vibebeat
dpkg-deb --build --root-owner-group $PKG
echo "Done: build/vibebeat_${VERSION}_amd64.deb"
