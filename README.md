## The streamline branch

This branch is a refactor in an orphan branch alongside the current `bradleyrp/factory` fork (actually rewrite) of `biophyscode/factory`.

## Development with `ortho`

In order to develop this code you must retrieve a subtree from `ortho`.

~~~
# initial setup
git remote add ortho-up http://github.com/bradleyrp/ortho
git subtree add --prefix=ortho ortho-up master
# later push and pull with
git subtree --prefix=ortho pull ortho-up master --squash
git subtree --prefix=ortho push ortho-up master
~~~
