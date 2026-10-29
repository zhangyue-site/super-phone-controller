# Public source configuration

This repository contains reusable source and neutral examples, not a live deployment.

- Supply service and download URLs through the documented build configuration; do not add personal domains, host addresses or private filesystem paths to source.
- Release builds require explicit configuration. Missing configuration must fail clearly rather than silently select someone else’s server.
- Keep device credentials, provider credentials, signing material, runtime configuration, private images, recordings and full-flash backups outside Git.
- Deployment examples must use placeholders and example paths. Do not commit actual service units or reverse-proxy configuration copied from a live server.
- The Android application ID and signing identity are compatibility settings. Changing them is not a substitute for removing private configuration.
- Synthetic fixtures and example private network addresses are not evidence of a real device or deployment.
- Check source, generated resources and all public branches before publishing. A passing pattern scan does not prove that no sensitive data exists.

After a history cleanup, re-clone the repository before contributing. Do not merge an old clone back into the cleaned history. Keep private runtime deployments separate from the public source checkout.
