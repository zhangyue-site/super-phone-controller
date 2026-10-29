#pragma once
#include <array>
#include <cstdint>
namespace controller {
constexpr std::array<uint8_t,7> absolute_touch_report(uint8_t buttons,uint16_t x,uint16_t y){return {{uint8_t(buttons&1),0,uint8_t(x),uint8_t(x>>8),uint8_t(y),uint8_t(y>>8),1}};}
}
