#!/usr/bin/env bash
# Shared container entrypoint for every palimpsest parser image (T17).
#
# The parser images have no SSH daemon by default; T14's RunPodSession reaches pods over
# *direct TCP SSH* (publicIp + mapped port 22), so each image now runs sshd. RunPod injects the
# pod's authorized public key into the env var $PUBLIC_KEY (set per-template at registration — it
# is NOT auto-injected). We append it to authorized_keys, start sshd, then idle so the container
# stays alive for RunPodSession to ssh/scp into and exec the parser.
set -eu

mkdir -p /root/.ssh && chmod 700 /root/.ssh
if [ -n "${PUBLIC_KEY:-}" ]; then
    printf '%s\n' "$PUBLIC_KEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi

ssh-keygen -A          # generate host keys on first boot
# sshd parses /etc/environment for every session (login + non-login), so the
# fabric `Connection.run()` non-login shell still gets /opt/venv/bin on PATH.
# Without this, T17 verify had to prepend `export PATH=...` to every command.
echo 'PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' > /etc/environment
/usr/sbin/sshd         # daemonize (sshd_config hardened in the image)
exec sleep infinity    # keep the container alive (replaces the old CMD ["sleep","infinity"])
