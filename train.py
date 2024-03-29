from __future__ import absolute_import
import timeit
import argparse
from os import path
import numpy as np
from keras import Model

from autoencoder.core.ae import AutoEncoder, load_ae_model, save_ae_model
from autoencoder.preprocessing.preprocessing import load_corpus, doc2vec
# from autoencoder.utils.keras_utils import Dense_tied
from autoencoder.utils.op_utils import vecnorm, add_gaussian_noise, add_masking_noise, add_salt_pepper_noise, revdict
from autoencoder.utils.io_utils import dump_json


def train(args):
    corpus = load_corpus(args.input)
    n_vocab, docs = len(corpus['vocab']), corpus['docs']
    corpus.clear()
    # vocab = corpus['vocab']
    corpus.clear() # save memory
    doc_keys = docs.keys()
    X_docs = []
    for k in doc_keys:
        X_docs.append(vecnorm(doc2vec(docs[k], n_vocab), 'logmax1', 0))
        del docs[k]
    X_docs = np.r_[X_docs]

    if args.noise == 'gs':
        X_docs_noisy = add_gaussian_noise(X_docs, 0.1)
    elif args.noise == 'sp':
        X_docs_noisy = add_salt_pepper_noise(X_docs, 0.1)
        pass
    elif args.noise == 'mn':
        X_docs_noisy = add_masking_noise(X_docs, 0.01)
    else:
        pass

    n_samples = X_docs.shape[0]
    np.random.seed(0)
    val_idx = np.random.choice(range(n_samples), args.n_val, replace=False)
    train_idx = list(set(range(n_samples)) - set(val_idx))
    X_train = X_docs[train_idx]
    X_val = X_docs[val_idx]
    del X_docs

    if args.noise:
        # X_train_noisy = X_docs_noisy[:-n_val]
        # X_val_noisy = X_docs_noisy[-n_val:]
        X_train_noisy = X_docs_noisy[train_idx]
        X_val_noisy = X_docs_noisy[val_idx]
        print 'added %s noise' % args.noise
    else:
        X_train_noisy = X_train
        X_val_noisy = X_val

    start = timeit.default_timer()

    ae = AutoEncoder(n_vocab, args.n_dim, comp_topk=args.comp_topk, ctype=args.ctype, save_model=args.save_model)
    ae.fit([X_train_noisy, X_train], [X_val_noisy, X_val], nb_epoch=args.n_epoch, \
            batch_size=args.batch_size, contractive=args.contractive)

    print 'runtime: %ss' % (timeit.default_timer() - start)

    if args.output:
        train_doc_codes = ae.encoder.predict(X_train)
        val_doc_codes = ae.encoder.predict(X_val)
        doc_keys = np.array(doc_keys)
        dump_json(dict(zip(doc_keys[train_idx].tolist(), train_doc_codes.tolist())), args.output + '.train')
        dump_json(dict(zip(doc_keys[val_idx].tolist(), val_doc_codes.tolist())), args.output + '.val')
        print 'Saved doc codes file to %s and %s' % (args.output + '.train', args.output + '.val')

    def unitmatrix(matrix, norm='l2', axis=1):
        if norm == 'l1':
            maxtrixlen = np.sum(np.abs(matrix), axis=axis)
        if norm == 'l2':
            maxtrixlen = np.linalg.norm(matrix, axis=axis)

        if np.any(maxtrixlen <= 0):
            return matrix
        else:
            maxtrixlen = maxtrixlen.reshape(1, len(maxtrixlen)) if axis == 0 else maxtrixlen.reshape(len(maxtrixlen), 1)
            return matrix / maxtrixlen

    def calc_pairwise_dev(weights):
        # the average squared deviation from 0 (90 degree)
        weights = unitmatrix(weights, axis=0)  # normalize
        n = weights.shape[1]
        score = 0.
        for i in range(n):
            for j in range(i + 1, n):
                score += (weights[:, i].dot(weights[:, j])) ** 2

        return np.sqrt(2. * score / n / (n - 1))

    from keras.models import load_model
    # import pandas as pd
    #
    # tw = np.empty(shape=[n_vocab, args.n_dim])
    # vocab = revdict(vocab)
    # for epoch in range(1, args.n_epoch + 1):
    #     file_name = "./checkpoint/" + str(epoch) + ".hdf5"
    #     print 'nnnn'
    #     autoencoder = load_ae_model(file_name)
    #     encoder = Model(autoencoder.input, autoencoder.get_layer('Encoded_Layer').output)
    #     print 'sss'
    #     topics = []
    #     weights = encoder.get_weights()[0]
    #     score = calc_pairwise_dev(weights)
    #     np.append(tw, weights)
    #     for idx in range(encoder.output_shape[1]):
    #         token_idx = np.argsort(weights[:, idx])[::-1]
    #         topics.append([(epoch, idx, vocab[x], weights[x, idx], score) for x in token_idx if x in vocab])
    #
    #     for topic in topics:
    #         temp_df = pd.DataFrame(topic, columns=['epoch', 'index', 'word', 'weight', 'score'])
    #         with open('./csvfiles/ae.csv', 'a') as f:
    #             temp_df.to_csv(f, index=False)
    #     print(epoch)
    # np.save('testnew', tw)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', type=str, required=True, help='path to the input corpus file')
    parser.add_argument('-nd', '--n_dim', type=int, default=128, help='num of dimensions (default 128)')
    parser.add_argument('-ne', '--n_epoch', type=int, default=100, help='num of epoches (default 100)')
    parser.add_argument('-bs', '--batch_size', type=int, default=100, help='batch size (default 100)')
    parser.add_argument('-nv', '--n_val', type=int, default=1000, help='size of validation set (default 1000)')
    parser.add_argument('-ck', '--comp_topk', type=int, help='competitive topk')
    parser.add_argument('-ctype', '--ctype', type=str, help='competitive type (kcomp, ksparse)')
    parser.add_argument('-cmodel', '--cmodel', type=str, help='model type')
    parser.add_argument('-sm', '--save_model', type=str, default='model', help='path to the output model')
    parser.add_argument('-contr', '--contractive', type=float, help='contractive lambda')
    parser.add_argument('--noise', type=str, help='noise type: gs for Gaussian noise, sp for salt-and-pepper or mn for masking noise')
    parser.add_argument('-o', '--output', type=str, help='path to the output doc codes file')
    args = parser.parse_args()

    if args.noise and not args.noise in ['gs', 'sp', 'mn']:
        raise Exception('noise arg should left None or be one of gs, sp or mn')
    train(args)

if __name__ == '__main__':
    main()