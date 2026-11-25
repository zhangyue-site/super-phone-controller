// 任务记录页 — 最近任务列表（HumanPillState.history，本地持久化）
// v1.4.23 HCI 改造：任务反馈闭环（可见性原则）
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'human_pill_state.dart';

class TaskHistoryPage extends StatelessWidget {
  const TaskHistoryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final items = List<Map<String, dynamic>>.from(HumanPillState.history);
    return Scaffold(
      appBar: AppBar(title: const Text('任务记录')),
      body: items.isEmpty
          ? const Center(
              child: Text('还没有任务记录\n被控共享开启后，收到的任务会显示在这里',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey)),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: items.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, i) {
                final rec = items[i];
                final ts = DateTime.fromMillisecondsSinceEpoch(
                    (rec['ts'] as num?)?.toInt() ?? 0);
                final running = rec['state'] == '运行中';
                final head = (rec['head'] ?? '') as String;
                final reply = (rec['reply'] ?? '') as String;
                return Card(
                  margin: EdgeInsets.zero,
                  child: ListTile(
                    leading: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(DateFormat('HH:mm').format(ts),
                            style: const TextStyle(
                                fontWeight: FontWeight.bold, fontSize: 13)),
                        Text(DateFormat('MM-dd').format(ts),
                            style: const TextStyle(
                                color: Colors.grey, fontSize: 11)),
                      ],
                    ),
                    title: Text(
                      head,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 14),
                    ),
                    subtitle: reply.isEmpty
                        ? null
                        : Text(reply,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 12, color: Colors.grey)),
                    trailing: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: running
                            ? Colors.blue.withValues(alpha: 0.15)
                            : Colors.green.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        rec['state'] ?? '',
                        style: TextStyle(
                          fontSize: 11,
                          color: running ? Colors.blue : Colors.green,
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
