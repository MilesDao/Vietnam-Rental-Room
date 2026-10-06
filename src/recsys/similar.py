"""Text-based ML for the app: "similar rooms" and free-text search.

TF-IDF on character 3-5-grams of title + description (works for Vietnamese without a word segmenter and
tolerates missing diacritics, since text is also ascii-folded), plus a small numeric part (log price,
log area, location) so "similar" also means similar price, size and place.
"""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from src.clean.text_clean import ascii_fold

TEXT_W = 0.6   # share of text similarity in "similar rooms"; the rest is price / area / location closeness


class Index:
    def __init__(self, d):
        self.ids = d.listing_id.to_numpy()
        self.pos = {lid: i for i, lid in enumerate(self.ids)}
        text = (d.title.fillna("") + " . " + d.description.fillna("").str[:600]).map(lambda t: ascii_fold(t) or "")
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=150_000,
                                   sublinear_tf=True)
        self.X = self.vec.fit_transform(text)
        num = pd.DataFrame({"p": np.log(d.price_vnd.astype(float)), "a": np.log(d.area_est.astype(float).clip(lower=5)),
                            "lat": d.latitude.astype(float), "lon": d.longitude.astype(float)})
        num = num.fillna(num.median())
        self.num = ((num - num.mean()) / num.std()).to_numpy()

    def similar(self, listing_id, k=8, among=None):
        """Top-k listing ids most like listing_id (optionally only among ids in `among`)."""
        i = self.pos[listing_id]
        text = linear_kernel(self.X[i], self.X).ravel()
        close = 1 / (1 + np.linalg.norm(self.num - self.num[i], axis=1))
        s = TEXT_W * text + (1 - TEXT_W) * close
        s[i] = -1
        if among is not None:
            s[~np.isin(self.ids, list(among))] = -1
        top = np.argsort(-s)[:k]
        return [self.ids[j] for j in top if s[j] > 0]

    def text_scores(self, query, ids):
        """Cosine similarity of a free-text query to each listing in ids (0..1)."""
        q = self.vec.transform([ascii_fold(query) or ""])
        rows = [self.pos[i] for i in ids]
        return linear_kernel(q, self.X[rows]).ravel()
