#!/bin/bash
# Rayboard — PipeWire virtual audio setup
# Creates: VirtualMic (null sink), VirtualMicSource (virtual mic), SoundpadOut (combine sink)
# Optionally routes a physical mic through VirtualMic via pw-loopback

# Detect default output sink unless overridden
REAL_SINK="${RAYBOARD_SINK:-$(pactl get-default-sink)}"
MIC_SOURCE="${RAYBOARD_MIC:-}"

pactl load-module module-null-sink \
    sink_name=VirtualMic \
    sink_properties=device.description="VirtualMic" 2>/dev/null || true

pactl load-module module-virtual-source \
    source_name=VirtualMicSource \
    master=VirtualMic.monitor \
    source_properties=device.description="VirtualMicSource" 2>/dev/null || true

pactl load-module module-combine-sink \
    sink_name=SoundpadOut \
    sink_properties=device.description="SoundpadOut" \
    slaves="${REAL_SINK},VirtualMic" 2>/dev/null || true

# If a mic source is configured, loopback it into VirtualMic
if [ -n "$MIC_SOURCE" ]; then
    exec pw-loopback -C "$MIC_SOURCE" -P VirtualMic
fi

# Keep the service alive
exec sleep infinity
