#!/bin/bash

echo "Running first-time setup..."
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Syu --noconfirm sudo ffmpeg v4l-utils

# Disable the service after first run
systemctl disable first-time-setup.service
