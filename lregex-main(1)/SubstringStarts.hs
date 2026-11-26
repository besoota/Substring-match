-- Use with the haskell/src directory of Agnishom/lregex.
module SubstringStarts (startPositions) where

import Data.List (elemIndices)
import qualified Extracted as E

-- | All zero-based boundaries where a match begins, in ascending order.
-- A successful zero-width match counts, including at the end of the input.
startPositions :: E.LRegex a -> [a] -> [Int]
startPositions regex input =
    let (_, valuations) = E.absEval E.cScanMatch input (outerLookAhead regex)
    in elemIndices [True] valuations

-- The trailing Sigma* lets the match end at any later or equal boundary.
outerLookAhead :: E.LRegex a -> E.LRegex a
outerLookAhead regex = E.LookAhead (E.Concat regex sigmaStar)
  where
    sigmaStar = E.Star (E.CharClass (const True))
