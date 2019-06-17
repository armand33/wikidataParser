import pickle
from processFunctions import get_subclasses, query_wikidata_dump, build_dataset


path = '/home/aboschin/datasets/wikidata/films/'
dump_path = '/home/public/wikidata/latest-all.json.bz2'
n_lines = 56208653

test_entities = get_subclasses('Q11424')  # sequence of images that give the impression of movement

query_wikidata_dump(dump_path, path, n_lines, test_entities=test_entities, collect_labels=False)

labels = pickle.load(open('/home/aboschin/datasets/wikidata/labels.pkl', 'rb'))
build_dataset(path, labels)