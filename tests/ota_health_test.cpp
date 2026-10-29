#include "ota_health_policy.h"
#include <cassert>
int main(){using controller::ota_local_health;
assert(!ota_local_health(44999999,true,44000000,44000000,true,12000));
assert(ota_local_health(45000000,true,45000000,45000000,true,8192));
assert(!ota_local_health(45000000,false,45000000,45000000,true,12000));
assert(!ota_local_health(45000000,true,42000000,45000000,true,12000));
assert(!ota_local_health(45000000,true,45000000,29000000,true,12000));
assert(!ota_local_health(45000000,true,45000000,45000000,false,12000));
assert(!ota_local_health(45000000,true,45000000,45000000,true,8191));
// No WAN parameter: offline maintenance is sufficient for boot confirmation.
}
