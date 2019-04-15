import pickle
import bz2
import json
import pandas as pd
import os

from tqdm import tqdm, tqdm_notebook


def get_labels_dict(path, path_pickle, n_lines):
    labels = {}
    fails = []

    dump = bz2.open(path+'latest-all.json.bz2', 'rt')
    progress_bar = tqdm(total=n_lines)

    line = dump.readline()  # the first line of the file should be "[\n" so we skip it
    counter = 0  # counter of the number of lines read

    while len(line) > 0:  # while there are lines to read
        counter += 1
        line = dump.readline().strip()
        progress_bar.update(1)
        if len(line) == 0:
            break
        try:
            if line[-1] == ',':
                line = line[:-1]  # all lines should end with a ','
        
            # turn string to json
            if line[0] != '{' or line[-1] != '}':
                # then this line is not a proper json file we should deal with it later
                fails.append(line)
                continue
            line = json.loads(line)

            # extract data from json
            id_ = get_id(line)
            labels[id_] = get_label(line)

        except:
            fails.append(line)

    dump_pickle(path_pickle, labels, 0)


def concat_claims(claims):
    """
    :param claims: dict
    :return: iterator through the claims
    """
    for rel_id, rel_claims in claims.items():
        for claim in rel_claims:
            yield claim


def to_triplets(ent):
    """
    :param ent: dict coming from the parsing of a json line of the dump
    :return: list of triplets of this entity (head, rel, tail)
    """
    if len(ent['claims']) == 0:
        return []
    claims = concat_claims(ent['claims'])
    triplets = []
    instanceof = []
    e1 = ent['id']
    for claim in claims:
        mainsnak = claim['mainsnak']
        if mainsnak['snaktype'] != "value":
            continue
        if mainsnak['datatype'] == 'wikibase-item':
            rel = mainsnak['property']
            e2 = 'Q{}'.format(mainsnak['datavalue']['value']['numeric-id'])
            triplets.append((e1, rel, e2))
            if rel == 'P31':
                instanceof.append(e2)
    return triplets, instanceof


def get_type(ent):
    return ent['type']


def get_id(ent):
    return ent['id']


def get_label(ent):
    """
    :param ent: dict coming from the parsing of a json line of the dump
    :return: string label of ent in english if available of any other language else
    """
    labels = ent['labels']
    if len(labels) == 0:
        return 'No label {}'.format(ent['id'])
    if 'en' in labels.keys():
        return labels['en']['value']
    else:
        return labels[list(labels.keys())[0]]['value']


def relabel(x, labels):
    try:
        l = labels[x]
        if ':' in l:
            return l[l.index(':')+1:]
        else:
            return l
    except KeyError:
        return x


def clean(str_):
    if str_[:31] == 'http://www.wikidata.org/entity/':
        return str_[31:]
    else:
        print('problem')
        return ''


def dump_pickle(path, triplet, n_dump):
    with open(path+'dump{}.pkl'.format(n_dump), 'wb') as f:
        pickle.dump(triplet, f)
    print('Just made pickle dump number {}'.format(n_dump))


def intersect(long_list, short_list):
    for i in long_list:
        if i in short_list:
            return True
    return False


def query_wikidata_dump(path, path_pickle, n_lines, query_tails):
    """
    :param path: path to the latest-all.json.bz2 file downloaded from
    https://dumps.wikimedia.org/wikidatawiki/entities/
    :param path_pickle: path to where pickle files will be written.
    :param n_lines: number of lines of the dump. Fastest way I found was
    `$ bzgrep -c ".*" latest-all.json.bz2`
    :param query_tails: list of entities to check if instance of.
    For each line (entity), we check if it as a fact of the type (id, query_rel, query_tail).
    :return:
    """
    human_facts = []
    fails = []

    dump = bz2.open(path+'latest-all.json.bz2', 'rt')
    progress_bar = tqdm(total=n_lines)

    line = dump.readline()  # the first line of the file should be "[\n" so we skip it
    counter = 0  # counter of the number of lines read
    n_pickle_dump = 0

    while len(line) > 0:  # while there are lines to read
        
        counter += 1
        line = dump.readline().strip()
        progress_bar.update(1)
        if len(line) == 0:
            break
        try:
            if line[-1] == ',':
                line = line[:-1]  # all lines should end with a ','
        
            # turn string to json
            if line[0] != '{' or line[-1] != '}':
                # then this line is not a proper json file we should deal with it later
                fails.append(line)
                continue
            line = json.loads(line)

            # extract data from json
            triplets, instanceof = to_triplets(line)

            if len(instanceof) > 0 and intersect(instanceof, query_tails):
                human_facts.extend(triplets)

        except:
            fails.append(line)

        if counter % 3000000 == 0:
            # dump in pickle to free memory
            n_pickle_dump += 1
            dump_pickle(path_pickle, (human_facts, fails), n_pickle_dump)

            # empty variables
            del human_facts, fails
            human_facts = []
            fails = []

    n_pickle_dump += 1
    dump_pickle(path_pickle, (human_facts, fails), n_pickle_dump)

    
def count_true_fails(fails):
    true_fails = 0
    for f in fails:
        try :
            if str(f) == ']':
                continue  # in this case it's the last line of the original dump file
            if len(f['claims']) > 0:
                true_fails += 1
        except:
            print(f)
    return true_fails


def concatpkls(n_dump, path_pickle, labels=None):
    df = pd.DataFrame(columns=['headEntity', 'relation', 'tailEntity'])

    for nd in tqdm_notebook(range(n_dump)):
        with open(path_pickle + 'dump{}.pkl'.format(nd + 1), 'rb') as f:
            facts, fails = pickle.load(f)
            true_fails = count_true_fails(fails)
            if true_fails > 0:
                print('{} true fails'.format(true_fails))
        df = pd.concat([df, pd.DataFrame(facts, columns=['headEntity', 'relation', 'tailEntity'])])
    df = df.drop_duplicates()

    if labels is not None:
        df['headEntity'] = df['headEntity'].apply(relabel, args=(labels,))
        df['relation'] = df['relation'].apply(relabel, args=(labels,))
        df['tailEntity'] = df['tailEntity'].apply(relabel, args=(labels,))

    return df


def write_csv(df, name):
    with open(name, 'w') as f:
        f.write('# Entities: {} \t Relations: {} \t Facts: {}\n'.format(
            len(set(df.headEntity).union(set(df.tailEntity))),
            df.relation.nunique(), len(df)))
        f.write('# headEntity \t tailEntity \t relation\n')
        df.to_csv(f, sep='\t', header=False, index=False)


def write_ent_dict(df, name):
    with open(name, 'w') as f:
        f.write('# Entities: {}\n'.format(len(df)))
        f.write('# entityID \t wikidataID \t label\n')
        df.to_csv(f, sep='\t', header=False, index=False)


def write_rel_dict(df, name):
    with open(name, 'w') as f:
        f.write('# Relations: {}\n'.format(len(df)))
        f.write('# relationID \t wikidataID \t label\n')
        df.to_csv(f, sep='\t', header=False, index=False)


def build_dataset(path, labels):
    """
    Print dataset in path (includes 4 files : edges (kg), features, entities, relations.
    :param path: path to the directory where there should already be a pickle/ directory.
    In the latter directory, all the .pkl files will be concatenated into one dataset.
    :param labels: dictionary coming from the function get_labels_dict
    """
    path_pickle = path + 'pickles/'
    n_files = len([name for name in os.listdir(path_pickle) if name[-4:] == '.pkl'])
    df = concatpkls(n_files, path_pickle)

    ents = list(df['headEntity'].unique())
    feats = list(set(df['tailEntity'].unique()) - set(ents))
    ent2ix = {ent: i for i, ent in enumerate(ents + feats)}
    ix2ent = {i: ent for ent, i in ent2ix.items()}

    tmp = df['relation'].unique()
    rel2ix = {rel: i for i, rel in enumerate(tmp)}
    ix2rel = {i: rel for rel, i in rel2ix.items()}

    df['headEntity'] = df['headEntity'].apply(lambda x: ent2ix[x])
    df['tailEntity'] = df['tailEntity'].apply(lambda x: ent2ix[x])
    df['relation'] = df['relation'].apply(lambda x: rel2ix[x])

    entities = pd.DataFrame([[i, ix2ent[i]] for i in range(len(ix2ent))],
                            columns=['entityID', 'wikidataID'])
    entities['label'] = entities['wikidataID'].apply(relabel, args=(labels,))

    relations = pd.DataFrame([[i, ix2rel[i]] for i in range(len(ix2rel))],
                             columns=['relationID', 'wikidataID'])
    relations['label'] = relations['wikidataID'].apply(relabel, args=(labels,))

    edges_mask = df.tailEntity.isin(df['headEntity'].unique())
    edges = df.loc[edges_mask, ['headEntity', 'tailEntity', 'relation']]
    features = df.loc[~edges_mask, ['headEntity', 'tailEntity', 'relation']]

    write_csv(edges, path + 'edges.txt')
    write_csv(features, path + 'features.txt')
    write_ent_dict(entities, path + 'entities.txt')
    write_rel_dict(relations, path + 'relations.txt')
