# Examples

## Using Ansible runtime

```python title="example.py"
{!../test/test_runtime_example.py!}
```

## Access to Ansible configuration

As you may not want to parse `ansible-config dump` yourself, you can make use of
a simple python class that facilitates access to it, using python data types.

```python
{!../test/test_configuration_example.py!}
```
