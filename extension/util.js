import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

/**
 * Executa o binário delux-battery de forma assíncrona.
 * Não bloqueia o processo do GNOME Shell.
 */
export function queryBatteryAsync(callback) {
    try {
        const binPath = GLib.find_program_in_path('delux-battery') || '/home/igazev/.local/bin/delux-battery';

        const proc = new Gio.Subprocess({
            argv: [binPath],
            flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        });
        proc.init(null);

        proc.communicate_utf8_async(null, null, (proc, res) => {
            try {
                const [, stdout] = proc.communicate_utf8_finish(res);
                if (stdout && stdout.trim().length > 0) {
                    const data = JSON.parse(stdout.trim());
                    callback(data);
                }
            } catch (e) {
                console.warn(`[DeluxBattery] Erro ao parsear retorno: ${e}`);
            }
        });
    } catch (e) {
        console.error(`[DeluxBattery] Erro no subprocesso: ${e}`);
    }
}
