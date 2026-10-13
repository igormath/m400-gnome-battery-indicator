import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import St from 'gi://St';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import { queryBatteryAsync } from './util.js';

// 1. O botão visual da barra superior
const DeluxIndicator = GObject.registerClass(
class DeluxIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Delux M400 Indicator', false);

        // Container horizontal (Flexbox)
        const box = new St.BoxLayout({
            style_class: 'panel-status-indicators-box',
            y_align: Clutter.ActorAlign.CENTER,
        });

        // Ícone do mouse
        this._icon = new St.Icon({
            icon_name: 'input-mouse-symbolic',
            style_class: 'system-status-icon',
        });
        box.add_child(this._icon);

        // Texto com a porcentagem
        this._label = new St.Label({
            text: '--%',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'delux-battery-label',
        });
        box.add_child(this._label);

        this.add_child(box);

        // Dropdown menu (when clicking the indicator)
        const titleItem = new PopupMenu.PopupMenuItem('Delux M400', { reactive: false });
        titleItem.label.style = 'font-weight: bold;';
        this.menu.addMenuItem(titleItem);

        this._statusMenuItem = new PopupMenu.PopupMenuItem('Battery: Checking...', { reactive: false });
        this.menu.addMenuItem(this._statusMenuItem);

        const refreshItem = new PopupMenu.PopupMenuItem('Refresh now');
        refreshItem.connect('activate', () => {
            this.refresh();
        });
        this.menu.addMenuItem(refreshItem);
    }

    refresh() {
        queryBatteryAsync((data) => {
            this.update(data);
        });
    }

    update(data) {
        if (!data || data.error) {
            this._label.set_text('Off');
            this._statusMenuItem.label.set_text('Mouse disconnected or idle');
            return;
        }

        const percentage = data.battery;
        const charging = data.charging;

        this._label.set_text(`${percentage}%`);

        if (charging) {
            this._icon.set_icon_name('battery-charging-symbolic');
            this._statusMenuItem.label.set_text(`Battery: ${percentage}% (Charging)`);
        } else {
            this._icon.set_icon_name('input-mouse-symbolic');
            this._statusMenuItem.label.set_text(`Battery: ${percentage}% (Discharging)`);
        }
    }
});

// 2. Extension Lifecycle
export default class DeluxBatteryExtension extends Extension {
    enable() {
        console.log('[DeluxBattery] Enabling Delux M400 extension...');

        this._indicator = new DeluxIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);

        // Primeira leitura imediata
        this._indicator.refresh();

        // Agendamento periódico a cada 60 segundos
        this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 60, () => {
            this._indicator.refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        console.log('[DeluxBattery] Disabling Delux M400 extension...');

        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = null;
        }

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
