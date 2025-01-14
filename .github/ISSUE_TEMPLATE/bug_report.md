---
name: Bug report
about: >
  Create a bug report. Ensure that it does reproduce on the main branch with
  python >=3.10.  For anything else, please use the discussion link below.
labels: bug, new
---

<!--- Verify first that your issue is not already reported on GitHub -->
<!--- Also test if the latest release and main branch are affected too -->

##### Summary

<!--- Explain the problem briefly below -->

##### Issue Type

- Bug Report

##### OS / ENVIRONMENT

<!--- Paste verbatim output between triple backticks -->

```console (paste below)
python -c "import ansible_compat; print(ansible_compat.__version__)"
```

<!--- Provide all relevant information below, e.g. target OS versions, network
 device firmware, etc. -->

- ansible installation method: one of source, pip, OS package
- ansible-compat installation method: one of source, pip, OS package

##### STEPS TO REPRODUCE

<!--- Describe exactly how to reproduce the problem, using a minimal test case -->

<!--- Paste example playbooks or commands between triple backticks below -->

```console (paste below)

```

<!--- HINT: You can paste gist.github.com links for larger files -->

##### Desired Behavior

<!--- Describe what you expected to happen when running the steps above -->

Possible security bugs should be reported via email to `security@ansible.com`

##### Actual Behavior

<!--- Describe what happened. If possible run with extra verbosity (-vvvv) -->

Please give some details of what is happening. Include a [minimum complete
verifiable example].

<!--- Paste verbatim command output between triple backticks -->

```paste below

```

[minimum complete verifiable example]: http://stackoverflow.com/help/mcve
