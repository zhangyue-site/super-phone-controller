import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/role_state.dart';
void main(){
 test('idle unarmed board permits planning but never implies overall readiness',(){
  const controller=RoleState(AppRole.controller,board:true,capture:false,relay:true);
  expect(controller.needsCapture,isFalse);expect(controller.canPrepare,isTrue);expect(controller.ready,isFalse);
  expect(const RoleState(AppRole.target,board:true,capture:true,relay:true).ready,isFalse);
  expect(const RoleState(AppRole.target,board:true,capture:true,relay:true,recentFrame:true,permission:true).ready,isTrue);
  for(final state in [const RoleState(AppRole.target,board:false,capture:true,relay:true,recentFrame:true,permission:true),const RoleState(AppRole.target,board:true,capture:true,relay:false,recentFrame:true,permission:true),const RoleState(AppRole.target,board:true,capture:true,relay:true,recentFrame:false,permission:true)]){expect(state.ready,isFalse);}
 });
}
