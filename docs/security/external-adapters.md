# External LLM Adapter Loading — Operator Guide

Calseta supports plugging in external LLM provider adapters so that an
organization can route through an internal LLM gateway, a private
Bedrock deployment, or any other backend without forking Calseta. This
document explains the **threat model** and the **two registration
paths** (one recommended, one deprecated).

If you only want the short answer: **package your adapter and declare
an entry point in the ``calseta.llm_adapters`` group**. Don't use the
``CALSETA_EXTERNAL_ADAPTERS`` env var unless you have a transitional
reason to.

---

## Threat model

The realistic attacker against this surface is an operator-adjacent
actor who has compromised one of:

- **The deployment ``.env`` file** (e.g. via stolen workstation, a
  leaked Vault token, or a misconfigured backup bucket).
- **The CI/CD pipeline** that renders environment variables into the
  running container (e.g. a malicious PR that mutates the workflow,
  a compromised secret store).

Such an attacker should not be able to load an arbitrary Python module
into the API process simply by editing one environment variable. The
old ``CALSETA_EXTERNAL_ADAPTERS=evil.module:Evil`` knob is exactly that
class of footgun: any importable module on the Python path becomes
executable code inside the request-handling process.

The S10 lockdown narrows that path:

1. The recommended registration route requires the adapter to be a
   real, installed package — meaning the attacker also needs the
   ability to land an extra dependency in the image build, which is a
   meaningfully higher bar than mutating an env var.
2. The legacy env-var path still works for back-compat but is
   deprecated and emits a structured warning on every load. Operators
   can grep for ``external_adapter.module_path_deprecated`` in their
   logs to find any remaining usage and migrate.

The provider-listing endpoint (``GET /v1/llm-integrations/providers``)
is also gated to ``admin`` scope. The list of installed external
adapters is operator-sensitive deployment topology and is not safe to
expose to a normal agents-read API key.

---

## Recommended: register via entry points

Calseta discovers adapters declared under the
``calseta.llm_adapters`` entry-point group at startup using
``importlib.metadata``. Any package installed in the same Python
environment as Calseta can register one or more adapters this way.

### Example ``pyproject.toml``

```toml
[project]
name = "mycompany-calseta-gateway"
version = "0.1.0"
dependencies = ["calseta"]

[project.entry-points."calseta.llm_adapters"]
gateway = "mycompany.llm_gateway:GatewayAdapter"
internal_bedrock = "mycompany.bedrock:InternalBedrockAdapter"
```

Each value is the same ``module.path:ClassName`` form the legacy env
var used. The class must subclass
``app.integrations.llm.base.LLMProviderAdapter`` and set
``provider_name`` and ``display_name`` class attributes.

### Install in the deployment image

Add the package to your Calseta container image (or to the same
virtualenv where ``calseta`` is installed). For example, in a custom
Dockerfile that extends the upstream image:

```Dockerfile
FROM ghcr.io/calseta/calseta-api:latest

USER root
RUN pip install --no-cache-dir mycompany-calseta-gateway==0.1.0
USER calseta
```

On startup you should see a structured log line per registered
adapter::

    external_adapter.registered provider_name=gateway source=entry_point ...

That confirms it loaded. From that point on, an ``LLMIntegration`` row
with ``provider="gateway"`` will be routed to ``GatewayAdapter``.

---

## Deprecated: ``CALSETA_EXTERNAL_ADAPTERS`` env var

The original registration path is still supported but discouraged:

```env
CALSETA_EXTERNAL_ADAPTERS=mycompany.llm_gateway:GatewayAdapter,acme.bedrock:BedrockAdapter
```

Each entry must be ``module.path:ClassName``. Calseta will
``importlib.import_module`` each module and pull the named class.

For each entry loaded this way you will get a warning log line::

    external_adapter.module_path_deprecated entry=mycompany.llm_gateway:GatewayAdapter ...

Treat that warning as a TODO. The env-var path will be removed in a
future major version. To migrate, package the adapter (see above) and
remove the env-var entry.

---

## Quick checklist

- [ ] Adapter class subclasses ``LLMProviderAdapter`` and sets
      ``provider_name`` and ``display_name``.
- [ ] Adapter is shipped as an installed Python package, not a loose
      module.
- [ ] ``pyproject.toml`` declares it under
      ``[project.entry-points."calseta.llm_adapters"]``.
- [ ] Image build pins the adapter package to a known version.
- [ ] No remaining ``CALSETA_EXTERNAL_ADAPTERS`` entries in the
      deployment ``.env`` (grep your logs for
      ``external_adapter.module_path_deprecated``).
- [ ] The API key used to call ``GET /v1/llm-integrations/providers``
      has the ``admin`` scope.
