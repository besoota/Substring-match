-- Use with the haskell/src directory of Agnishom/lregex.
module SubstringStarts (startPositions) where

import Data.List (elemIndices)
import qualified Extracted as E

-- | All zero-based boundaries where a match begins, in ascending order.
-- A successful zero-width match counts, including at the end of the input.
startPositions :: E.LRegex a -> [a] -> [Int]
startPositions r w =
    let regex = E.LookAhead (E.Concat r wildCard)
        (_, evaluation) = E.absEval E.cScanMatch w regex
    in elemIndices [True] evaluation
