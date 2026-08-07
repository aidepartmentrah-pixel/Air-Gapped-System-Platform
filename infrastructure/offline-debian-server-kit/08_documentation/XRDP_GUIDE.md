# XRDP Remote Desktop Guide

xrdp lets you connect to this Debian server's existing graphical desktop from a Windows
PC using the built-in **Remote Desktop Connection** app (`mstsc`) — no extra client
software needed on the Windows side.

This kit assumes the offline server **already has a desktop environment installed**
(GNOME, KDE, XFCE, etc.), including its Xorg display server. xrdp itself does not provide
a desktop — it just exposes whatever desktop session is already configured for your user
to a remote RDP client.

## Why `xorgxrdp` is also included

`10_remote_desktop/` bundles both `xrdp` (the RDP protocol server) and `xorgxrdp` (the
Xorg driver that lets xrdp attach directly to your existing Xorg session). Without
`xorgxrdp`, xrdp falls back to starting a separate Xvnc-based desktop instead of showing
your actual logged-in session — not what you want here.

`xorgxrdp` itself depends on the X server stack (`xserver-xorg-core` and its libraries).
Since the target already has a full desktop installed, those are expected to already be
present — the matching `.deb` files are bundled in `10_remote_desktop/` anyway purely as a
safety net in case any piece is missing, and are harmless no-ops (`dpkg` skips a package
that's already at the same version) if already installed.

## Installing

```
bash 07_install_scripts/install_xrdp.sh
```

This installs `xrdp`, `xorgxrdp`, and every dependency from `10_remote_desktop/`, then
enables and starts the `xrdp` service automatically. Uses local files only — no internet
required. **Always run this on the whole folder together** (`dpkg -i 10_remote_desktop/*.deb`,
which is what the script does) — running `dpkg -i` on a single file like `xrdp*.deb` alone
will fail with unmet dependency errors, since dpkg only resolves install order across the
set of files given in one invocation.

## Connecting from Windows

1. On the Windows machine, press `Win + R`, type `mstsc`, press Enter.
2. In the **Computer** field, type the offline server's IP address (find it on the
   server with `hostname -I`).
3. Click **Connect**.
4. Log in with the same Linux username/password you use on the server directly.

## Desktop-environment-specific notes

- **XFCE**: works out of the box with xrdp — no extra configuration needed.
- **KDE Plasma**: generally works out of the box; if the session appears blank, check
  `~/.xsession` exists and starts `startplasma-x11`.
- **GNOME**: xrdp does **not** reliably support a full GNOME Shell session out of the
  box (a known upstream limitation — GNOME Shell depends on features xrdp's X11 backend
  doesn't fully provide). If the offline server runs GNOME as its primary desktop and the
  RDP session appears blank or crashes:
  - Confirm whether a lighter alternate session (e.g. "GNOME on Xorg" vs "GNOME") is
    selectable at the login greeter over RDP.
  - If GNOME Shell does not work reliably over RDP, this is expected — physical/local
    console access remains the reliable path for the primary desktop, and xrdp is best
    used here mainly for terminal work, DBeaver, or Obsidian rather than full desktop use.

## Checking xrdp is running

```
sudo systemctl status xrdp --no-pager
```
Expected: `Active: active (running)`.

## Port and firewall

xrdp listens on TCP port **3389** by default. If the offline server has a firewall
(`ufw`, `nftables`, etc.) make sure port 3389 is allowed from the network segment
operators will connect from:
```
sudo ss -tlnp | grep 3389
```
Expected: a line showing `xrdp` listening on `0.0.0.0:3389` or `*:3389`.

## Security note

RDP sessions authenticate with the same Linux username/password as local login. Use a
strong password for any account that will be reachable over xrdp, and restrict network
access to port 3389 to trusted subnets only (e.g. the hospital's internal IT network),
since this server has no internet exposure but may still be reachable from a wider
internal network than intended.
