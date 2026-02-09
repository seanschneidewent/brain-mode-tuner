'''
name = input("what is your name? ")

if name == "Sean":
    print("welcome boss")
elif name == "Ember":
    print("hello, thats me! ")
elif name == "marc":
    print("hello, im marc! ")
else:
    print("hello "+ name)
'''

'''
names = ["Sean", "Marc", "Ember", "Bob"]

for name in names:
    if name == "Sean":
        print("welcome boss")
    elif name == "Ember":
        print("hello, that's me!")  
    else:
        print("hello " + name)
'''

def greet(name):
    if name == "Sean":
        print("welcome boss")
    elif name == "Ember":
        print("hello, thats me!")
    else:
        print("hello" + name)

names = ["Sean", "Marc", "Ember", "Bob"]

for name in names:
    greet(name)