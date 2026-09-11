# P002 translation runtime

P002 uses Co-op Translator only through its provider-free, agent-assisted
Markdown API. P002 keeps all article paths, source bindings, language-pack
approval, review records, QC, final Output and admission decisions. The
runtime must not be configured with an LLM provider by this integration.

Install it in the isolated P002 environment:

```powershell
Projects/P002-นักเขียนบทวิเคราะห์/work/translation-env/Scripts/python.exe -m pip install -r Projects/P002-นักเขียนบทวิเคราะห์/Repo/requirements-translation.txt
```

Locked upstream artifact:

| distribution | version | license | wheel SHA256 |
| --- | --- | --- | --- |
| `co-op-translator` | `0.20.1` | MIT | `3716f945b95d99607e437ec99019ad705e0eeb271e625eb1aba95e0f79e3c239` |

The dependency tree is intentionally isolated under `work/translation-env`.
It is not committed as source and it never writes P002 final Output directly.
