FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends wine64 xvfb xauth libgl1-mesa-dri fonts-liberation fonts-wine && rm -rf /var/lib/apt/lists/*
ENV WINEPREFIX=/opt/phocus-wine WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml,winemenubuilder.exe=" LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:77
COPY phocus/ /opt/phocus/
COPY python/ /opt/winpy/
COPY worker.py /opt/worker.py
RUN Xvfb :77 -ac -screen 0 1024x768x24 -nolisten tcp >/tmp/display.log 2>&1 & pid=$!; sleep 1; /usr/lib/wine/wine64 wineboot.exe -u && /usr/lib/wine/wineserver -w && cp /usr/share/wine/fonts/tahoma*.ttf "$WINEPREFIX/drive_c/windows/Fonts/"; rc=$?; kill "$pid" || true; exit "$rc"
ENTRYPOINT ["/bin/sh","-c","export DISPLAY=:78; Xvfb :78 -ac -screen 0 1024x768x24 -nolisten tcp 1>&2 & sleep 1; exec /usr/lib/wine/wine64 'Z:\\opt\\winpy\\python.exe' -u 'Z:\\opt\\worker.py'"]
