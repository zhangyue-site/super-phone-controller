import 'package:flutter/material.dart';
import 'controller_local_vision.dart';
import 'product_widgets.dart';

/// Persistent observation state; model errors never block task controls.
class ControllerModelStatus extends StatelessWidget {
  const ControllerModelStatus(
      {super.key, required this.vision, required this.onRetry});
  final ControllerLocalVision vision;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Card(
        child: ExpansionTile(
          key: const PageStorageKey('controller-local-observation'),
          title: const Text('本地按钮识别'),
          subtitle: Semantics(liveRegion: true, child: Text(vision.status)),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          children: [
            const Text('只提供观察提示；准备期间仍可发送任务。'),
            if (vision.inferenceMs != null || vision.boxCount != null)
              Text([
                if (vision.inferenceMs != null)
                  '实际推理 ${vision.inferenceMs!.toStringAsFixed(1)} 毫秒',
                if (vision.boxCount != null) '按钮 ${vision.boxCount} 个',
              ].join(' · ')),
            if (vision.error != null) ...[
              ProductError(vision.error!),
              OutlinedButton(
                onPressed: vision.preparing ? null : onRetry,
                child: const Text('重试本地识别'),
              ),
            ],
          ],
        ),
      );
}
