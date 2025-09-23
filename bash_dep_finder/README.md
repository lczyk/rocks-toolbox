# bash_dep_finder

Find dependencies of a bash script.

```bash
$ bash_dep_finder --lines some_example_script.sh
cat 16
mktemp 40
apt 45,69,69,75
find 47,216
mv 50,114,122,138,146
sudo 71,71,77
tree 94,165
rm 99,111,118,126,135,142,150,156
mkdir 101,113,121,137,145
cp 102
ar 107
tar 110,117,125,134,141,149
ls 168
fzf 216,222
apt-cache 222
cut 222
```

Can also output to `--json` and accept multiple files as input.