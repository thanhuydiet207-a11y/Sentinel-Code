import { expect, test } from 'claude-code/testing';

test('/secops-pane mở bảng trạng thái và cập nhật bộ đếm công cụ', async ($, on) => {
  // Đăng ký các stub trả lời thay cho Claude Code trong môi trường kiểm thử
  on('store.get', () => 0);
  on('store.set', () => ({}));
  on('command.register', () => ({}));
  on('ui.open', () => ({ isOpened: true }));
  on('ui.invalidate', () => ({}));
  on('tool.call', () => ({ result: 'ok' }));

  // Khởi chạy sự kiện bắt đầu phiên
  await $.session.start({});

  // Giả lập 2 lần gọi công cụ (1 lệnh Bash và 1 lần sửa tệp Edit)
  await $.tool.call({ tool: 'Bash', command: 'git status' });
  await $.tool.call({ tool: 'Edit', file_path: 'src/index.ts' });

  // Chạy lệnh /secops-pane để mở bảng trạng thái
  const cmdResult = await $.command.run({ command: 'secops-pane', args: '' });
  expect(cmdResult).toEqual({});
});
