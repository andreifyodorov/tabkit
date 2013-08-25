import sys

class TabkitException(Exception):
    pass

def handle_exceptions(main):
    try:
        main()
    except TabkitException as e:
        print >> sys.stderr, "%s: %s" % (sys.argv[0], e)
