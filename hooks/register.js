// ==============================================================================
// Claude Code Mod (Hooks Module): hooks/register.js
// Tài liệu tham chiếu:
//   - Create a Mod: https://code.claude.com/docs/en/plugins/mods/create
//   - Draw in the Interface: https://code.claude.com/docs/en/plugins/mods/interface
//   - Mods Reference: https://code.claude.com/docs/en/plugins/mods/reference
// ==============================================================================
let totalToolCalls = 0;
let fileEditsCount = 0;
let bashCallsCount = 0;
let lastAuditedTarget = 'Chưa chạy kiểm toán';
let activeTab = 'overview';

export function register(on, options) {
  on('session.start', async ($, e, next) => {
    const savedEdits = await $.store.get('secops_file_edits');
    if (typeof savedEdits === 'number') fileEditsCount = savedEdits;
    await $.command.register({
      name: 'secops-pane',
      description: 'Mở bảng trạng thái kiểm toán bảo mật SecOps trên Terminal',
      immediate: true,
    });
    return next(e);
  });

  on('command.run', { command: 'secops-pane' }, async ($) => {
    await $.ui.open({
      id: 'secops-dashboard',
      title: 'SecOps Audit Status',
      focus: true,
      width: '35%',
    });
    return {};
  });

  on('tool.call', async ($, e, next) => {
    totalToolCalls += 1;
    if (e.tool === 'Edit' || e.tool === 'Write' || e.tool === 'MultiEdit') {
      fileEditsCount += 1;
      await $.store.set('secops_file_edits', fileEditsCount);
    } else if (e.tool === 'Bash') {
      bashCallsCount += 1;
    }
    if (e.tool === 'Skill' && e.input && e.input.skill) {
      lastAuditedTarget = String(e.input.skill);
    }
    await $.ui.invalidate('ui.render');
    return next(e);
  });

  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    if (totalToolCalls === 0) return next(e);
    return next({
      ...e,
      props: {
        ...e.props,
        suffix: ` · SecOps [Tools: ${totalToolCalls} | Edits: ${fileEditsCount}]…`,
      },
    });
  });

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== 'secops-dashboard') return next(e);
    const { Box, Text, Button } = $.ui.resolve(e);
    return Box({
      direction: 'column',
      gap: 1,
      padding: 1,
      children: [
        Text({ weight: 'semibold', children: ['Bảng Trạng Thái Kiểm Toán SecOps'] }),
        Box({
          direction: 'row',
          gap: 1,
          children: [
            Button({
              key: 'tab-overview',
              label: activeTab === 'overview' ? '[1: Tổng quan]' : '1: Tổng quan',
              hotkey: '1',
              onPress: async () => {
                activeTab = 'overview';
                await $.ui.invalidate('ui.render');
              },
            }),
            Button({
              key: 'tab-actions',
              label: activeTab === 'actions' ? '[2: Tác vụ]' : '2: Tác vụ',
              hotkey: '2',
              onPress: async () => {
                activeTab = 'actions';
                await $.ui.invalidate('ui.render');
              },
            }),
          ],
        }),
        activeTab === 'overview'
          ? Box({
              direction: 'column',
              gap: 0,
              children: [
                Text({ children: [`• Tổng lượt gọi công cụ: ${totalToolCalls}`] }),
                Text({ children: [`• Số lần sửa tệp (Edit/Write): ${fileEditsCount}`] }),
                Text({ children: [`• Số lệnh Bash đã chạy: ${bashCallsCount}`] }),
                Text({ children: [`• Kỹ năng gần nhất: ${lastAuditedTarget}`] }),
              ],
            })
          : Box({
              direction: 'column',
              gap: 1,
              children: [
                Button({
                  key: 'btn-reset-counters',
                  label: 'Đặt lại bộ đếm (Phím r)',
                  hotkey: 'r',
                  onPress: async () => {
                    totalToolCalls = 0;
                    fileEditsCount = 0;
                    bashCallsCount = 0;
                    await $.store.delete('secops_file_edits');
                    await $.ui.invalidate('ui.render');
                  },
                }),
                Button({
                  key: 'btn-close-pane',
                  label: 'Đóng bảng (Phím q)',
                  hotkey: 'q',
                  onPress: async () => {
                    await $.ui.close({ id: 'secops-dashboard' });
                  },
                }),
              ],
            }),
      ],
    });
  });
}
