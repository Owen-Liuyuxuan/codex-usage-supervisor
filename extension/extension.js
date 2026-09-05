/* exported init */

'use strict';

const { Clutter, Gio, GLib, GObject, St } = imports.gi;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

const BUS_NAME = 'io.github.owen.CodexUsageSupervisor';
const OBJECT_PATH = '/io/github/owen/CodexUsageSupervisor';

const DBUS_XML = `
<node>
  <interface name="${BUS_NAME}">
    <method name="GetSummary">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <method name="Refresh">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <signal name="UsageChanged">
      <arg name="summary" type="s"/>
    </signal>
  </interface>
</node>`;

const UsageProxy = Gio.DBusProxy.makeProxyWrapper(DBUS_XML);

function compactNumber(value) {
    const number = Number(value || 0);
    if (number >= 1000000)
        return `${(number / 1000000).toFixed(1)}M`;
    if (number >= 1000)
        return `${(number / 1000).toFixed(0)}K`;
    return `${number}`;
}

function windowName(minutes) {
    if (minutes && minutes % 1440 === 0)
        return `${minutes / 1440}-day allowance`;
    if (minutes && minutes % 60 === 0)
        return `${minutes / 60}-hour allowance`;
    return 'Codex allowance';
}

function resetText(value) {
    if (!value)
        return 'Reset time unavailable';
    const target = new Date(value);
    if (Number.isNaN(target.getTime()))
        return 'Reset time unavailable';
    const minutes = Math.max(0, Math.ceil((target.getTime() - Date.now()) / 60000));
    if (minutes < 60)
        return `Resets in ${minutes} min`;
    if (minutes < 1440)
        return `Resets in ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
    return `Resets in ${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}

function relativeTime(value) {
    if (!value)
        return '';
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60)
        return 'now';
    if (seconds < 3600)
        return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400)
        return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
}

class ProgressLine {
    constructor(accentClass) {
        this.actor = new St.Widget({ style_class: 'codex-progress-track' });
        this._fill = new St.Widget({ style_class: `codex-progress-fill ${accentClass}` });
        this.actor.add_child(this._fill);
        this.setFraction(0);
    }

    setFraction(value) {
        const fraction = Math.min(1, Math.max(0, Number(value) || 0));
        this._fill.set_width(Math.round(320 * fraction));
    }
}

const CodexIndicator = GObject.registerClass(
class CodexIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Codex Usage Supervisor', false);

        const panelBox = new St.BoxLayout({ style_class: 'codex-panel-box' });
        this._panelIcon = new St.Icon({
            icon_name: 'utilities-terminal-symbolic',
            style_class: 'system-status-icon codex-panel-icon',
        });
        this._panelLabel = new St.Label({
            text: 'Codex —',
            y_align: Clutter.ActorAlign.CENTER,
        });
        panelBox.add_child(this._panelIcon);
        panelBox.add_child(this._panelLabel);
        this.add_child(panelBox);

        this._buildPopover();
        this._connectService();
    }

    _buildPopover() {
        const item = new PopupMenu.PopupBaseMenuItem({ reactive: false, can_focus: false });
        const body = new St.BoxLayout({ vertical: true, style_class: 'codex-popover' });
        item.add_child(body);

        const header = new St.BoxLayout({ style_class: 'codex-header' });
        header.add_child(new St.Label({ text: 'CODEX', style_class: 'codex-wordmark', x_expand: true }));
        this._liveLabel = new St.Label({ text: '● LOCAL', style_class: 'codex-live' });
        header.add_child(this._liveLabel);
        body.add_child(header);

        this._primaryValue = new St.Label({ text: '—', style_class: 'codex-hero-value' });
        body.add_child(this._primaryValue);
        this._primaryCaption = new St.Label({ text: 'Waiting for local usage data', style_class: 'codex-caption' });
        body.add_child(this._primaryCaption);
        this._primaryBar = new ProgressLine('codex-progress-primary');
        body.add_child(this._primaryBar.actor);

        const secondaryHeader = new St.BoxLayout({ style_class: 'codex-secondary-header' });
        this._secondaryName = new St.Label({ text: 'Long-term allowance', x_expand: true });
        this._secondaryValue = new St.Label({ text: '—', style_class: 'codex-secondary-value' });
        secondaryHeader.add_child(this._secondaryName);
        secondaryHeader.add_child(this._secondaryValue);
        body.add_child(secondaryHeader);
        this._secondaryBar = new ProgressLine('codex-progress-secondary');
        body.add_child(this._secondaryBar.actor);
        this._secondaryReset = new St.Label({ text: '', style_class: 'codex-reset' });
        body.add_child(this._secondaryReset);

        body.add_child(new St.Widget({ style_class: 'codex-divider' }));
        body.add_child(new St.Label({ text: 'TODAY', style_class: 'codex-section-label' }));
        const stats = new St.BoxLayout({ style_class: 'codex-stats' });
        [
            ['tasks', 'TASKS'],
            ['focus', 'FOCUS'],
            ['tokens', 'TOKENS'],
        ].forEach(([key, label]) => {
            const column = new St.BoxLayout({ vertical: true, style_class: 'codex-stat', x_expand: true });
            this[`_${key}Value`] = new St.Label({ text: '—', style_class: 'codex-stat-value' });
            column.add_child(this[`_${key}Value`]);
            column.add_child(new St.Label({ text: label, style_class: 'codex-stat-label' }));
            stats.add_child(column);
        });
        body.add_child(stats);

        body.add_child(new St.Widget({ style_class: 'codex-divider' }));
        body.add_child(new St.Label({ text: 'RECENT ACTIVITY', style_class: 'codex-section-label' }));
        this._recentBox = new St.BoxLayout({ vertical: true, style_class: 'codex-recent-list' });
        body.add_child(this._recentBox);

        this.menu.addMenuItem(item);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const refresh = new PopupMenu.PopupMenuItem('Refresh now');
        refresh.connect('activate', () => this._requestRefresh());
        this.menu.addMenuItem(refresh);
        const preferences = new PopupMenu.PopupMenuItem('Preferences');
        preferences.connect('activate', () => this._openPreferences());
        this.menu.addMenuItem(preferences);
    }

    _connectService() {
        this._proxy = new UsageProxy(
            Gio.DBus.session,
            BUS_NAME,
            OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    this._showError('Service unavailable');
                    return;
                }
                this._signalId = proxy.connectSignal('UsageChanged', (_proxy, _sender, [summary]) => {
                    this._applySummary(summary);
                });
                proxy.GetSummaryRemote((result, callError) => {
                    if (callError)
                        this._showError('Could not read usage');
                    else
                        this._applySummary(result[0]);
                });
            }
        );
    }

    _applySummary(serialized) {
        let summary;
        try {
            summary = JSON.parse(serialized);
        } catch (_error) {
            this._showError('Invalid service response');
            return;
        }
        if (summary.error) {
            this._showError(summary.error);
            return;
        }

        const limits = summary.rate_limits || {};
        const primary = limits.primary;
        const secondary = limits.secondary;
        if (primary) {
            const percent = Math.round(primary.used_percent);
            this._panelLabel.text = `Codex ${percent}%`;
            this._primaryValue.text = `${percent}% used`;
            this._primaryCaption.text = `${windowName(primary.window_minutes)}  ·  ${resetText(primary.resets_at)}`;
            this._primaryBar.setFraction(percent / 100);
            this._setUrgency(percent);
        } else {
            this._panelLabel.text = 'Codex —';
            this._primaryValue.text = 'No allowance data';
            this._primaryCaption.text = 'Start or refresh a Codex task';
            this._primaryBar.setFraction(0);
        }

        if (secondary) {
            this._secondaryName.text = windowName(secondary.window_minutes);
            this._secondaryValue.text = `${Math.round(secondary.used_percent)}% used`;
            this._secondaryReset.text = resetText(secondary.resets_at);
            this._secondaryBar.setFraction(secondary.used_percent / 100);
        } else {
            this._secondaryValue.text = 'Not reported';
            this._secondaryReset.text = '';
            this._secondaryBar.setFraction(0);
        }

        const today = summary.today || {};
        this._tasksValue.text = `${today.sessions || 0}`;
        this._focusValue.text = `${today.focus_minutes || 0} min`;
        this._tokensValue.text = compactNumber(today.tokens);
        this._renderRecent(summary.recent || []);
        this._liveLabel.text = '● LOCAL';
        this._liveLabel.remove_style_class_name('codex-error');
    }

    _renderRecent(items) {
        this._recentBox.get_children().forEach(child => child.destroy());
        if (!items.length) {
            this._recentBox.add_child(new St.Label({ text: 'No recent tasks', style_class: 'codex-empty' }));
            return;
        }
        items.slice(0, 3).forEach(item => {
            const row = new St.BoxLayout({ style_class: 'codex-recent-row' });
            row.add_child(new St.Label({ text: '●', style_class: 'codex-activity-dot' }));
            const text = new St.BoxLayout({ vertical: true, x_expand: true });
            text.add_child(new St.Label({
                text: item.name || 'Untitled task', style_class: 'codex-task-name',
                x_align: Clutter.ActorAlign.START,
            }));
            text.add_child(new St.Label({
                text: item.project || item.model || '', style_class: 'codex-task-meta',
                x_align: Clutter.ActorAlign.START,
            }));
            row.add_child(text);
            row.add_child(new St.Label({ text: relativeTime(item.updated_at), style_class: 'codex-task-time' }));
            this._recentBox.add_child(row);
        });
    }

    _setUrgency(percent) {
        this._panelLabel.remove_style_class_name('codex-warning');
        this._panelLabel.remove_style_class_name('codex-critical');
        if (percent >= 95)
            this._panelLabel.add_style_class_name('codex-critical');
        else if (percent >= 80)
            this._panelLabel.add_style_class_name('codex-warning');
    }

    _requestRefresh() {
        if (!this._proxy)
            return;
        this._liveLabel.text = '● REFRESHING';
        this._proxy.RefreshRemote((result, error) => {
            if (error)
                this._showError('Refresh failed');
            else
                this._applySummary(result[0]);
        });
    }

    _openPreferences() {
        try {
            Gio.Subprocess.new(
                ['codex-usage-supervisor-preferences'],
                Gio.SubprocessFlags.NONE
            );
        } catch (error) {
            Main.notifyError('Codex Usage Supervisor', `Could not open preferences: ${error.message}`);
        }
    }

    _showError(message) {
        this._panelLabel.text = 'Codex !';
        this._liveLabel.text = '● OFFLINE';
        this._liveLabel.add_style_class_name('codex-error');
        this._primaryValue.text = 'Unavailable';
        this._primaryCaption.text = message;
    }

    destroy() {
        if (this._proxy && this._signalId)
            this._proxy.disconnectSignal(this._signalId);
        this._proxy = null;
        super.destroy();
    }
});

class Extension {
    enable() {
        this._indicator = new CodexIndicator();
        Main.panel.addToStatusArea('codex-usage-supervisor', this._indicator);
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}

function init() {
    return new Extension();
}
