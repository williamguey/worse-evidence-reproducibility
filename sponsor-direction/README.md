# Sponsor-direction comparison: offline reproduction

This archive reproduces one targeted GPT-5.6 Luna comparison on 312 numerical
cases previously used in the construct-validation bank. The calls are new; the
cases are reused and must not be counted as an additional independent sample
or pooled with earlier calls. The design has neutral, sponsor endorses worse,
and sponsor endorses better conditions, with both display orders (1,872 cells).
The sponsor-target sentence is the only difference between the two endorsed
arms. The task concerns a forced report purchase with an exact expected loss
under stipulated optimal subsequent action; it does not isolate a psychological
mechanism or establish performance in open-ended agents.

Collection month: October 2026. The requested configuration was GPT-5.6 Luna
(`openai/gpt-5.6-luna`) through OpenRouter, pinned to OpenAI only with fallback
disabled. Reasoning was disabled; output used a strict JSON schema containing
only choice A or B, with a 768 generated-token cap. Temperature, top-p and top-k
were omitted, retaining endpoint defaults. These settings and the exact prompt
messages are supplied for interpreting the recorded calls and future replication.

Run `python3 reproduce.py` with Python 3.9 or newer. No packages, API credentials,
network, model downloads or new model calls are needed. The script verifies the
file manifest, computes exact report totals from rational parameters, scores
all available choices, retains unavailable planned choices, and reproduces the
three predeclared whole-case contrasts and Holm3 results against expected.json.
All six responses for one case are nested within the same analysis unit.
Inference assumes independence across whole cases; missing-outcome bounds do
not address dependence from a shared service.

The primary family is worse minus better (endorsement direction), worse minus
neutral (worsening), and neutral minus better (improvement). Fixed six-product
betting mixtures provide one-sided positive tests; Holm3 adjusts these tests.
Nominal and familywise 95% missing-outcome envelope intervals use fixed-mixture
inversion (Bonferroni3 for the familywise intervals). A valid-response fraction
of at least 95% in each arm was the technical completeness rule, independent of
accuracy, effect direction or significance. All outcomes are retained.

Contents: data/cases.json has rational numerical parameters; data/plan.json has
the full factorial identities and fixed schedule; data/outcomes.json has only
scientific choices or explicit unavailability; data/prompts.json has exact
messages and generation settings for every planned cell; science.py is an
independent, standard-library reproduction implementation. Provider routing
price caps, transport logs, request/generation IDs from the service, reasoning
traces and private accounting are not necessary for these calculations and
are excluded. Model identifier and generation settings are retained. No model
weights or third-party datasets are redistributed.
