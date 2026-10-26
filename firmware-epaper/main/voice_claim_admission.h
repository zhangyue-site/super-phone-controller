#pragma once
namespace controller {
inline bool admit_remote_claim(bool claimed,bool current,bool idle,bool held,bool conversation,bool preparing,bool diagnostic){
 return claimed&&current&&idle&&!held&&!conversation&&!preparing&&!diagnostic;
}
}
