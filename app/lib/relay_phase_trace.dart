/// Fixed-field diagnostics only. This observer cannot grant authority or retry.
class RelayPhaseTrace {
  RelayPhaseTrace({required this.onEvent, Duration Function()? elapsed}) {
    final watch=Stopwatch()..start();
    _elapsed=elapsed ?? ()=>watch.elapsed;
  }
  final void Function(Map<String,Object>) onEvent;
  late final Duration Function() _elapsed;
  Duration _since=Duration.zero;
  int _attempt=0;
  int? _op,_seq;
  bool _active=false,_writeStarted=false;
  String _phase='unknown';
  static const phases={'attach','poll','maintenance','mode','write','read','ack','detach','shutdown'};
  void begin(String phase,{int? op}) {
    finish();_attempt++;_op=op;_seq=null;_writeStarted=false;
    _active=true;_phase=phases.contains(phase)?phase:'unknown';_since=_elapsed();
    _emit('phase_begin');
  }
  void setAction(int op,int seq){_op=op;_seq=seq;}
  void phase(String value,{bool clearAction=false}) {
    if(!_active)return;
    _emit('phase_end');
    if(clearAction){_op=null;_seq=null;_writeStarted=false;}
    _phase=phases.contains(value)?value:'unknown';_since=_elapsed();_emit('phase_begin');
  }
  void markWriteStarted(){_writeStarted=true;}
  void finish(){if(_active){_emit('phase_end');_active=false;}}
  String get _failureKind => _op==12 ? 'maintenance_unconfirmed' : _op==11 ? 'ota_unconfirmed' :
      const {1,2,3,4,13,14}.contains(_op) ? (_writeStarted?'input_outcome_unknown':'input_not_dispatched') :
      const {5,6,7}.contains(_op) ? 'control_unconfirmed' : 'transport_unconfirmed';
  void fail(Object error){if(_active){_emit('phase_failure',error:error);_active=false;}}
  void _emit(String reason,{Object? error}) {
    final type=error?.runtimeType.toString();
    final row=<String,Object>{'event':'relay_phase','phase':_phase,'reason':reason,
      'attempt':_attempt,'stage_ms':(_elapsed()-_since).inMilliseconds.clamp(0,600000),
      'write_started':_writeStarted,
      if(_op!=null && _op!>=1 && _op!<=14)'op':_op!,
      if(_seq!=null && _seq!>=0 && _seq!<=0xffffffff)'seq':_seq!,
      if(error!=null)'failure_kind':_failureKind,
      if(error!=null)'error_type':const {'TimeoutException','StateError','FormatException','ControlHttpFailure','PlatformException','ClientException'}.contains(type)?type!:'Unknown'};
    try{onEvent(Map<String,Object>.unmodifiable(row));}catch(_){/* Diagnostics never change transport outcome. */}
  }
}
