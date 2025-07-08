from flamapy.metamodels.fm_metamodel.transformations import UVLReader


def main():
    fm = UVLReader("tests/models/fm10_constraints.uvl").transform()
    print(fm)
    

if __name__ == "__main__":
    main()