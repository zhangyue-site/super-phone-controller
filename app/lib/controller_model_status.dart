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
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('控制手机本机模型', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Semantics(liveRegion: true, child: Text(vision.status)),
            const Text('在控制手机本机识别被控画面中的按钮，仅作为观察提示。'),
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
                  child: const Text('重试准备本机模型')),
            ],
          ]),
        ),
      );
}
