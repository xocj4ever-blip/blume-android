#!/bin/sh

# Gradle startup script for Blume Android App
#
# Licensed under the Apache License, Version 2.0

set -e

APP_HOME=$(cd "$(dirname "$0")" && pwd)

if command -v gradle >/dev/null 2>&1; then
    exec gradle "$@"
elif [ -f "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" ]; then
    exec java -jar "$APP_HOME/gradle/wrapper/gradle-wrapper.jar" "$@"
else
    echo "Gradle wrapper or gradle command not found."
    echo "To build on Android Studio: open folder '$APP_HOME'"
    echo "To build via CLI: install gradle or run on machine with gradle."
    exit 1
fi
