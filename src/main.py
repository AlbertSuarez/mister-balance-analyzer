import argparse


def parse_args():
    parser = argparse.ArgumentParser(description='Mister Balance Analyzer')
    parser.add_argument('--input_html', type=str, required=True, help='Input HTMLfile')
    parser.add_argument('--output_pdf', type=str, required=True, help='Output PDF file')
    args = parser.parse_args()
    return args


def main(input_html, output_pdf):
    pass


if __name__ == '__main__':
    args = parse_args()
    main(args.input_html, args.output_pdf)
