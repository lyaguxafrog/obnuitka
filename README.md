# Obnuitka

> ⚠️ In development - API may change

Format Python code for Nuitka compilation.

## Install

```bash
pip install -e .
```

## Usage

```bash
obnuitka path/to/file.py        # → .obnuitka/file.py
obnuitka path/to/dir/          # → .obnuitka/ with project tree
obnuitka path -f               # format in place
obnuitka path -o custom/       # custom output directory
```

## What it does

- Removes docstrings and comments
- Removes type hints
- Minifies variable names (`users_list` → `a`)
- Joins simple statements with `;`

## Example

Input:
```python
def calculate_sum(numbers: list[int]) -> int:
    total = 0
    for num in numbers:
        total += num
    return total

def double(x: int) -> int:
    """Some docstring"""
    return x * 2

# some comments
class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def get_info(self) -> str:
        return f"{self.name} is {self.age}"
```

Output:
```python
def calculate_sum(numbers):
    a = 0
    for b in numbers:
        a += b
    return a
def double(x):return x * 2
class User:
    def __init__(self, name, age):self.name = name;self.age = age
    def get_info(self):return f'{self.name} is {self.age}'
```
