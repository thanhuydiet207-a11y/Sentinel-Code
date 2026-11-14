import { describe, expect, test, tier } from 'claude-code/testing';

tier('user');

describe('register', () => {
  test('registers /secops-pane and opens its dashboard', async ($, on) => {
    const registeredCommands: string[] = [];
    const openedPanes: string[] = [];

    on('store.get', () => ({ value: undefined }));
    on('store.set', () => ({ value: undefined }));
    on('session.start', ($, e) => ({ cwd: e.cwd }));
    on('command.register', ($, e) => {
      registeredCommands.push(e.name);
      return { value: { command: e.name } };
    });
    on('ui.open', ($, e, next) => {
      openedPanes.push(e.id);
      return next(e);
    });

    await $.session.start({
      surface: 'terminal',
      isInteractive: true,
      cwd: '/work',
    });

    const result = await $.command.run({
      command: 'secops-pane',
      args: '',
      origin: { kind: 'composer' },
      presentation: { isFullscreen: true, columns: 120 },
    });

    expect(registeredCommands).toContain('secops-pane');
    expect(openedPanes).toContain('secops-dashboard');
    expect(result).toEqual({});
  });
});
