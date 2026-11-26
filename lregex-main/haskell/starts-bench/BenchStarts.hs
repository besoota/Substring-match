module Main (main) where

import Control.DeepSeq (force)
import Control.Exception (evaluate)
import Control.Monad (forM_, replicateM, replicateM_, unless)
import Data.IORef (IORef, newIORef, readIORef)
import Data.List (intercalate)
import Data.Word (Word64)
import GHC.Clock (getMonotonicTimeNSec)
import System.Environment (getArgs)
import System.Exit (die)
import System.Mem (performGC)
import Text.Read (readMaybe)

import qualified Extracted as E
import SubstringStarts (startPositions)
import Utils (lreSize, wildCard)

-- wildCard in Utils denotes Sigma*, including the empty string.
containsAhead :: Char -> E.LRegex Char
containsAhead c =
    E.LookAhead (E.Concat (E.Concat wildCard (E.CharClass (== c))) wildCard)

data Benchmark = Benchmark
    { patternName :: String
    , notation :: String
    , expression :: E.LRegex Char
    , expectedOnAab :: [Int]
    }

benchmarks :: [Benchmark]
benchmarks =
    let manyA = E.Star (E.CharClass (== 'a'))
        hasB = containsAhead 'b'
    in [ Benchmark "nested_star_with_lookahead" "(a*)*(?=.*b.*)"
             (E.Concat (E.Star manyA) hasB) [0, 1, 2]
       , Benchmark "star_with_lookahead" "a*(?=.*b.*)"
             (E.Concat manyA hasB) [0, 1, 2]
       , Benchmark "two_lookaheads" "(?=.*a.*)(?=.*b.*)"
             (E.Concat (containsAhead 'a') hasB) [0, 1]
       ]

-- Read the arguments in IO on every call. Only the prepared input and AST
-- are shared across trials; the result of the pure match must be computed anew.
{-# NOINLINE measureOnce #-}
measureOnce :: IORef (E.LRegex Char, String) -> IO (Word64, Int)
measureOnce workload = do
    (regex, input) <- readIORef workload
    performGC
    start <- getMonotonicTimeNSec
    positions <- evaluate (force (startPositions regex input))
    end <- getMonotonicTimeNSec
    let count = length positions
    unless (count == 0) (die "Unexpected match on a^n")
    pure (end - start, count)

runLength :: Int -> Int -> Int -> IO ()
runLength n warmups repetitions = do
    input <- evaluate (force (replicate n 'a'))
    putStrLn "pattern_name,regex,text_length,repetition,elapsed_ns,match_count"
    forM_ benchmarks $ \benchmark -> do
        let regex = expression benchmark
        -- lreSize traverses the complete AST before the first timed call.
        _ <- evaluate (lreSize regex)
        unless (startPositions regex "aab" == expectedOnAab benchmark) $
            die ("Positive control failed for " ++ notation benchmark)
        workload <- newIORef (regex, input)
        replicateM_ warmups (measureOnce workload)
        samples <- replicateM repetitions (measureOnce workload)
        forM_ (zip [1 :: Int ..] samples) $ \(trial, (elapsed, count)) ->
            putStrLn (intercalate ","
                [patternName benchmark, notation benchmark, show n, show trial,
                 show elapsed, show count])

main :: IO ()
main = do
    args <- getArgs
    case traverse readMaybe args of
        Just [n, warmups, repetitions]
            | n >= 0 && warmups >= 0 && repetitions > 0 ->
                runLength n warmups repetitions
        _ -> die "Usage: bench-starts LENGTH WARMUPS REPETITIONS"
