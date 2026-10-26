#pragma once
namespace controller {
inline bool voice_ready(bool direct_network,bool legacy_ready,bool server,bool chat,bool asr){
 return direct_network ? server&&chat&&asr : legacy_ready;
}
inline bool voice_can_probe(bool direct_network,bool legacy_ready){return direct_network||legacy_ready;}
}
