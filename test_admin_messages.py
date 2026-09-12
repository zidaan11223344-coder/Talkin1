from pathlib import Path

source = Path('bot.py').read_text(encoding='utf-8')
assert 'جارٍ تنفيذ' not in source
assert 'سأرسل النجاح بعد تأكيد الخادم' not in source
assert 'لم يؤكد الخادم تنفيذ العملية' not in source
assert 'self.send_room_text(room, labels.get(changed_role' in source
for role in ('kicked', 'outcast', 'member', 'admin', 'owner'):
    assert f'"{role}"' in source
print('admin messages: PASS')
