import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/control_screen.dart';

class RpcBoard extends BleOtaService {
  final calls=<Map<String,dynamic>>[];
  @override bool get supportsControl=>true;
  @override Future<Map<String,dynamic>> controlRequest(Map<String,dynamic> body) async {
    calls.add(body);
    if(body['operation']=='skills')return {'skills':[{'id':'weather','name':'查看天气','description':'打开浏览器查看天气结果','requirements':['B保持解锁'],'parameters':[{'name':'task','label':'任务目标','value':'打开浏览器搜索天气'}]}]};
    return {'state':'pending','task_id':'a'*32,'reply':'计划：打开浏览器搜索天气','terminal':false};
  }
}
void main() {
  test('production control client sends generic tasks over BLE only',() async {
    final b=RpcBoard(),c=ControlClient();await c.authorize(b);
    final out=await c.command('prepare',text:'打开地图搜索公园');
    expect(out['state'],'pending');expect(b.calls.single,{'operation':'prepare','text':'打开地图搜索公园'});c.close();
    await expectLater(ControlClient().authorize(BleOtaService()),throwsFormatException);
  });
  testWidgets('skill buttons show descriptions and prepare without auto-confirm',(tester)async {
    final b=RpcBoard();
    await tester.pumpWidget(MaterialApp(home:ControlScreen(service:b)));
    await tester.pumpAndSettle();
    expect(find.textContaining('当前支持打开微信找联系人'),findsNothing);
    expect(find.text('共享整屏给 AI'),findsNothing);
    await tester.tap(find.text('查看专项技能'));await tester.pumpAndSettle();
    expect(find.text('查看天气'),findsOneWidget);expect(find.text('打开浏览器查看天气结果'),findsOneWidget);
    await tester.tap(find.text('使用技能'));await tester.pumpAndSettle();
    await tester.tap(find.text('预览计划'));await tester.pumpAndSettle();
    expect(b.calls.last['operation'],'skill');expect(b.calls.last['skill_id'],'weather');
    expect(b.calls.any((c)=>c['operation']=='confirm'),isFalse);
    expect(find.text('确认执行'),findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
