#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace controller {
constexpr unsigned in_endpoint_count(const uint8_t* p,std::size_t n){unsigned mask=0;for(std::size_t i=0;i+1<n;){unsigned len=p[i];if(len<2||i+len>n)return 255;if(p[i+1]==5&&len>=7&&(p[i+2]&128))mask|=1u<<(p[i+2]&15);i+=len;}unsigned count=0;for(unsigned i=0;i<16;++i)count+=(mask>>i)&1;return count;}
template<std::size_t N> constexpr std::array<uint8_t,N-7> without_cdc_notification(const uint8_t (&raw)[N]){
 std::array<uint8_t,N-7> out{};std::size_t to=0;
 for(std::size_t i=0;i+1<N;){unsigned len=raw[i];if(len<2||i+len>N)break;
  if(raw[i+1]==5&&len==7&&raw[i+2]==0x81){i+=len;continue;}
  auto start=to;for(unsigned j=0;j<len&&to<out.size();++j)out[to++]=raw[i+j];
  if(raw[i+1]==5&&len==7&&raw[i+2]==0x85)out[start+2]=0x81;
  if(raw[i+1]==4&&len>=9&&raw[i+5]==2&&raw[i+6]==2)out[start+4]=0;
  if(raw[i+1]==36&&len==4&&raw[i+2]==2)out[start+3]&=~2u;
  i+=len;
 }
 out[2]=out.size()&255;out[3]=(out.size()>>8)&255;return out;
}
}
