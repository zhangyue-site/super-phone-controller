import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:pcflash/screen_share.dart";
import "package:pcflash/usb_launch.dart";
import "package:pcflash/usb_target_screen.dart";
void main() {
 testWidgets("active USB screen share offers control connection without stopping capture", (tester) async {
  var selected = 0;
  final messenger=TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(ScreenShare.channel, (call) async {
   if (call.method=="status") return "{\"active\":true,\"capture\":\"共享中\",\"task\":\"\"}";
   if (call.method=="stop") fail("Switching control must not stop screen capture");
   return null;
  });
  await tester.pumpWidget(MaterialApp(home:UsbTargetScreen(attachment:const UsbAttachment("AABBCCDDEEFF","session",null,null),isCurrent:()=>true,onLegacy:()=>selected++)));
  await tester.pump(); await tester.pump(const Duration(seconds:1));
  expect(find.text("连接云端控制"),findsOneWidget);
  await tester.tap(find.text("连接云端控制")); await tester.pump();
  expect(selected,1);
  await tester.pumpWidget(const SizedBox());
  messenger.setMockMethodCallHandler(ScreenShare.channel,null);
 });
}
