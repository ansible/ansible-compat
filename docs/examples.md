# Examples

## Using Ansible runtime

```{literalinclude} ../test/test_runtime_example.py
:language: python
```

## Access to Ansible configuration

As you may not want to parse `ansible-config dump` yourself, you
can make use of a simple python class that facilitates access to
it, using python data types.

```{literalinclude} ../test/test_configuration_example.py
:language: python
```
