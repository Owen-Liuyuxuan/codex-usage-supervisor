#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${project_dir}/pyproject.toml")"
package_root="$(mktemp -d)"
trap 'rm -rf -- "${package_root}"' EXIT
chmod 0755 "${package_root}"

install -d "${package_root}/DEBIAN" \
  "${package_root}/usr/lib/python3/dist-packages/codex_usage_supervisor" \
  "${package_root}/usr/bin" \
  "${package_root}/usr/lib/systemd/user" \
  "${package_root}/usr/share/applications" \
  "${package_root}/usr/share/dbus-1/services" \
  "${package_root}/usr/share/gnome-shell/extensions/codex-usage-supervisor@owen.local" \
  "${package_root}/usr/share/icons/hicolor/scalable/apps" \
  "${package_root}/usr/share/doc/codex-usage-supervisor"

install -m 0644 "${project_dir}"/src/codex_usage_supervisor/*.py \
  "${package_root}/usr/lib/python3/dist-packages/codex_usage_supervisor/"
install -m 0644 "${project_dir}/packaging/codex-usage-supervisor.desktop" \
  "${package_root}/usr/share/applications/"
install -m 0644 "${project_dir}/packaging/codex-usage-supervisor.svg" \
  "${package_root}/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 "${project_dir}/packaging/io.github.owen.CodexUsageSupervisor.service" \
  "${package_root}/usr/share/dbus-1/services/"
install -m 0644 "${project_dir}/packaging/codex-usage-supervisor.service" \
  "${package_root}/usr/lib/systemd/user/"
install -m 0644 "${project_dir}"/extension/* \
  "${package_root}/usr/share/gnome-shell/extensions/codex-usage-supervisor@owen.local/"
install -m 0644 "${project_dir}/README.md" \
  "${package_root}/usr/share/doc/codex-usage-supervisor/"

cat > "${package_root}/usr/bin/codex-usage-supervisor" <<'EOF'
#!/usr/bin/env bash
exec python3 -m codex_usage_supervisor.preferences "$@"
EOF
chmod 0755 "${package_root}/usr/bin/codex-usage-supervisor"

cat > "${package_root}/usr/bin/codex-usage-supervisor-service" <<'EOF'
#!/usr/bin/env bash
exec python3 -m codex_usage_supervisor.service "$@"
EOF
chmod 0755 "${package_root}/usr/bin/codex-usage-supervisor-service"

cat > "${package_root}/usr/bin/codex-usage-supervisor-preferences" <<'EOF'
#!/usr/bin/env bash
exec python3 -m codex_usage_supervisor.preferences "$@"
EOF
chmod 0755 "${package_root}/usr/bin/codex-usage-supervisor-preferences"

cat > "${package_root}/DEBIAN/control" <<EOF
Package: codex-usage-supervisor
Version: ${version}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gnome-shell (>= 42)
Maintainer: Owen
Description: GNOME top-panel addon for supervising Codex usage
 Shows local Codex allowance, token, task, and focus-time metrics in a modern
 GNOME Shell popover backed by an on-demand private D-Bus service.
EOF

cat > "${package_root}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
EOF
chmod 0755 "${package_root}/DEBIAN/postinst"

cat > "${package_root}/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
EOF
chmod 0755 "${package_root}/DEBIAN/postrm"

mkdir -p "${project_dir}/dist"
dpkg-deb --root-owner-group --build "${package_root}" \
  "${project_dir}/dist/codex-usage-supervisor_${version}_all.deb"
